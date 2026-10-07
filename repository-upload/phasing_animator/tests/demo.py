# SPDX-License-Identifier: GPL-3.0-or-later
"""Small original pavilion scene for reproducible tests and screenshots."""
from PySide6.QtGui import QVector3D as V
from core.scene import Scene
from core.mesh import Mesh
from core.group import Group
from core.layers import Layer
from phasing_animator import engine as e


def box(x,y,z,w,d,h,color):
    pts=[V(x,y,z),V(x+w,y,z),V(x+w,y+d,z),V(x,y+d,z),
         V(x,y,z+h),V(x+w,y,z+h),V(x+w,y+d,z+h),V(x,y+d,z+h)]
    m=Mesh()
    for ring in ((3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)):
        f=m.add_face([pts[i] for i in ring]);f.attrs={'color':color,'back':True}
    return m


def scene():
    s=Scene();s.layers += [Layer(n) for n in ('Foundation','Structure','Envelope','Roof')]
    objects=[('Foundation',box(-3,-2,0,6,4,.3,(.52,.61,.69)))]
    for x in (-2.7,2.4):
        for y in (-1.7,1.4):objects.append(('Structure',box(x,y,.3,.3,.3,3.2,(.28,.48,.60))))
    objects.extend([('Envelope',box(-2.7,1.5,.3,5.4,.12,2.7,(.38,.68,.77))),('Envelope',box(2.5,-1.7,.3,.12,3.2,2.7,(.38,.68,.77))),('Roof',box(-3,-2,3.5,6,4,.25,(.75,.80,.82)))])
    for i,(name,mesh) in enumerate(objects):
        g=Group(mesh,f'{name} {i+1}');g.layer=name;s.groups.append(g)
    data=e.empty_data();data['edition']='pro'
    for i,name in enumerate(('Foundation','Structure','Envelope','Roof')):
        p=e.add_phase(data,name,i*3);p['effect']='fade' if name=='Envelope' else 'rise';p['rise']=2
    s.plugin_data[e.KEY]=data
    return s
