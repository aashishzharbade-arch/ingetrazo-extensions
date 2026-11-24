"""Read self-contained glTF 2 binary characters for the viewport preview."""
import base64
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np
from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QColor, QImage

TYPES = {5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
WIDTH = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}


def rotation(q):
    x,y,z,w = q / max(np.linalg.norm(q), 1e-12)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def sample(track, time):
    times, values, interpolation, prop = track
    i = max(0, times.searchsorted(time, side='right')-1)
    j = min(i+1, len(times)-1)
    span = times[j]-times[i]
    t = np.clip((time-times[i])/span,0,1) if span else 0.
    if interpolation == 'CUBICSPLINE':
        a,b = values[3*i+1],values[3*j+1]
        return ((2*t**3-3*t*t+1)*a + (t**3-2*t*t+t)*span*values[3*i+2]
                + (-2*t**3+3*t*t)*b + (t**3-t*t)*span*values[3*j])
    a,b = values[i],values[j]
    if interpolation == 'STEP' or i==j:return a
    if prop == 'rotation':
        dot = np.dot(a,b)
        if dot<0:b,dot=-b,-dot
        if dot<.9995:
            theta=np.arccos(np.clip(dot,-1,1))
            return (np.sin((1-t)*theta)*a+np.sin(t*theta)*b)/np.sin(theta)
    return a*(1-t)+b*t


class Character:
    def __init__(self, path):
        self.path=Path(path)
        raw=self.path.read_bytes()
        magic,version,length=struct.unpack_from('<4sII',raw)
        if (magic,version,length)!=(b'glTF',2,len(raw)):raise ValueError('Choose a binary glTF 2.0 (.glb) file.')
        cursor=12
        chunks={}
        while cursor<len(raw):
            n,kind=struct.unpack_from('<I4s',raw,cursor)
            cursor+=8
            if cursor+n>len(raw):raise ValueError('Incomplete GLB chunk.')
            chunks[kind]=memoryview(raw)[cursor:cursor+n]
            cursor+=n
        self.doc=json.loads(bytes(chunks[b'JSON']))
        self.bin=chunks[b'BIN\0']
        if self.doc.get('extensionsRequired'):raise ValueError('Export a standard GLB with compression and required material extensions disabled.')
        self.arrays={}
        self.nodes=self.doc['nodes']
        self.order=[]
        seen=set()
        def visit(i,parent):
            if i in seen:raise ValueError('Invalid GLB scene hierarchy.')
            seen.add(i)
            self.order.append((i,parent))
            for child in self.nodes[i].get('children',[]):visit(child,i)
        for i in self.doc['scenes'][self.doc.get('scene',0)].get('nodes',[]):visit(i,None)
        self.parts=[]
        indices=[];uvs=[];self.batches=[]
        offset=draw_start=0
        for i,_ in self.order:
            n=self.nodes[i]
            if 'mesh' not in n:continue
            skin=self.doc['skins'][n['skin']] if 'skin' in n else None
            for prim in self.doc['meshes'][n['mesh']]['primitives']:
                if prim.get('mode',4)!=4:continue
                a=prim['attributes'];pos=self.array(a['POSITION'])
                index=self.array(prim['indices']).ravel() if 'indices' in prim else np.arange(len(pos))
                if index.dtype.kind not in 'iu' or len(index)%3 or np.any(index>=len(pos)):raise ValueError('Invalid triangle indices.')
                mat=self.doc.get('materials',[])[prim['material']] if 'material' in prim else {}
                pbr=mat.get('pbrMetallicRoughness',{})
                tex=pbr.get('baseColorTexture',{})
                uv_name='TEXCOORD_'+str(tex.get('texCoord',0))
                uv=self.array(a[uv_name])[index].copy() if uv_name in a else np.zeros((len(index),2))
                uv[:,1]=1-uv[:,1]
                uvs.append(uv);indices.append(index.astype('int64')+offset)
                self.batches.append((self.texture(pbr),draw_start,len(index)))
                bind=None
                if skin and 'JOINTS_0' in a:
                    ids=np.array(skin['joints'])
                    if not set(ids).issubset(seen):raise ValueError('Skin joints must belong to the active scene.')
                    matrices=(self.array(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
                              if 'inverseBindMatrices' in skin else np.tile(np.eye(4),(len(ids),1,1)))
                    js=[];ws=[]
                    for suffix in ('0','1'):
                        if 'JOINTS_'+suffix in a:
                            js.append(self.array(a['JOINTS_'+suffix]))
                            ws.append(self.array(a['WEIGHTS_'+suffix]))
                    joints=np.concatenate(js,axis=1);weights=np.concatenate(ws,axis=1)
                    if np.any(joints>=len(ids)):raise ValueError('Invalid skin joint index.')
                    weights=weights/np.maximum(weights.sum(1,keepdims=True),1e-10)
                    bind=(ids,matrices,joints,weights)
                self.parts.append((i,pos,bind))
                offset+=len(pos);draw_start+=len(index)
        if not indices:raise ValueError('The selected scene contains no triangle meshes.')
        self.idx=np.concatenate(indices)
        self.uv=np.concatenate(uvs)
        self.clips=[]
        for anim in self.doc.get('animations',[]):
            tracks={}
            for channel in anim['channels']:
                dst=channel['target'];prop=dst['path']
                if prop not in ('translation','rotation','scale') or dst.get('node') not in seen:continue
                sm=anim['samplers'][channel['sampler']]
                times=self.array(sm['input']).ravel()
                values=self.array(sm['output'])
                interp=sm.get('interpolation','LINEAR')
                if not len(times) or len(values)!=len(times)*(3 if interp=='CUBICSPLINE' else 1):
                    raise ValueError('Invalid GLB animation track.')
                tracks[(dst['node'],prop)]=(times,values,interp,prop)
            if tracks:self.clips.append((anim.get('name') or f'Clip {len(self.clips)+1}',tracks))
        self.mapping={}
        rest=self.geometry({},0)
        if not np.isfinite(rest).all():raise ValueError('Invalid character positions.')
        lo=rest.min(0);hi=rest.max(0)
        self.origin=(lo+hi)/2;self.origin[1]=lo[1]
        if hi[1]-lo[1]<1e-6:raise ValueError('The character has no height along the glTF up axis.')
        self.scale=1.78/(hi[1]-lo[1])

    def view(self,i):
        v=self.doc['bufferViews'][i]
        if v.get('buffer',0)!=0:raise ValueError('Embed all buffers in the GLB.')
        start=v.get('byteOffset',0);end=start+v['byteLength']
        if start<0 or end>len(self.bin):raise ValueError('Invalid GLB buffer range.')
        return self.bin[start:end]

    def array(self,i):
        if i in self.arrays:return self.arrays[i]
        a=self.doc['accessors'][i]
        if 'sparse' in a:raise ValueError('Re-export this GLB with sparse accessors disabled.')
        v=self.doc['bufferViews'][a['bufferView']]
        dtype=np.dtype(TYPES[a['componentType']]);width=WIDTH[a['type']]
        arr=np.ndarray((a['count'],width),dtype,buffer=self.view(a['bufferView']),offset=a.get('byteOffset',0),
                       strides=(v.get('byteStride',width*dtype.itemsize),dtype.itemsize))
        if a.get('normalized'):
            arr=np.maximum(-1,arr.astype('f4')/np.iinfo(dtype).max)
        self.arrays[i]=arr
        return arr

    def texture(self,pbr):
        factor=pbr.get('baseColorFactor',[1,1,1,1])
        data=b''
        if 'baseColorTexture' in pbr:
            source=self.doc['textures'][pbr['baseColorTexture']['index']]['source']
            img=self.doc['images'][source]
            if 'bufferView' in img:data=bytes(self.view(img['bufferView']))
            elif img.get('uri','').startswith('data:'):data=base64.b64decode(img['uri'].split(',',1)[1])
            else:raise ValueError('Embed character textures in the GLB.')
        folder=Path(os.environ.get('LOCALAPPDATA') or QStandardPaths.writableLocation(QStandardPaths.CacheLocation))/'ingetrazo'/'game-play-textures'
        folder.mkdir(parents=True,exist_ok=True)
        target=folder/(hashlib.sha256(data+bytes(str(factor),'ascii')).hexdigest()+'.png')
        if target.is_file():return str(target)
        if data:
            image=QImage.fromData(data).convertToFormat(QImage.Format_RGBA8888)
            if image.isNull():raise ValueError('Could not decode the embedded character texture.')
            if any(v!=1 for v in factor):
                pixels=np.frombuffer(image.bits(),dtype='u1').reshape(image.height(),image.width(),4)
                pixels[:]=np.rint(pixels*np.asarray(factor)).astype('u1')
        else:
            image=QImage(2,2,QImage.Format_RGBA8888)
            image.fill(QColor.fromRgbF(*factor))
        from PySide6.QtCore import QSaveFile,QIODevice
        file=QSaveFile(str(target))
        if not file.open(QIODevice.WriteOnly) or not image.save(file,'PNG') or not file.commit():
            raise OSError('Could not cache the character texture.')
        return str(target)

    def geometry(self,tracks,t):
        matrices={}
        for i,parent in self.order:
            node=self.nodes[i]
            if 'matrix' in node:m=np.asarray(node['matrix']).reshape(4,4).T
            else:
                def value(prop,default):
                    track=tracks.get((i,prop))
                    return sample(track,t) if track else np.asarray(node.get(prop,default))
                m=np.eye(4)
                m[:3,:3]=rotation(value('rotation',[0,0,0,1]))*value('scale',[1,1,1])
                m[:3,3]=value('translation',[0,0,0])
            matrices[i]=matrices[parent]@m if parent is not None else m
        result=[]
        for i,pos,skin in self.parts:
            if skin is None:
                m=matrices[i];result.append(pos@m[:3,:3].T+m[:3,3]);continue
            ids,inv,joints,weights=skin
            bones=(np.stack([matrices[j] for j in ids])@inv)[:,:3,:].astype('f4')
            coords=np.zeros_like(pos,dtype='f4')
            for column in range(joints.shape[1]):
                w=weights[:,column]
                if not np.any(w):continue
                mat=bones[joints[:,column]]
                coords+=(np.einsum('nij,nj->ni',mat[:,:,:3],pos)+mat[:,:,3])*w[:,None]
            result.append(coords)
        return np.concatenate(result)

    def prepare_motion(self):
        self.motion={}
        # The authored rest mesh is centered vertically, while the clips
        # place the rig on the floor. Calibrate against the animated T-pose.
        reference=dict(self.clips)['T-Pose']
        pose=self.geometry(reference,0)
        low,high=pose.min(0),pose.max(0)
        self.origin=(low+high)/2
        self.origin[1]=low[1]
        self.scale=1.78/(high[1]-low[1])
        for name,tracks in self.clips:
            duration=max(track[0][-1] for track in tracks.values())
            travel=np.zeros(3)
            if name in ('Walking','Running'):
                # The imported clips advance through space. Let collision-tested
                # player motion supply this displacement exactly once.
                travel=(self.geometry(tracks,duration)-self.geometry(tracks,0)).mean(axis=0)
                travel[1]=0
            self.motion[name]=(tracks,duration,travel)

    def frame(self,name,phase):
        tracks,duration,travel=self.motion[name]
        points=(self.geometry(tracks,phase*duration)-phase*travel-self.origin)*self.scale
        return np.column_stack((points[:,0],-points[:,2],points[:,1])).astype('f4')
