# Publish these three extensions

1. Open repository-upload. Upload its CONTENTS (not the enclosing folder and not this ZIP) into your GitHub repository using Add file → Upload files. The three extension folders and README.md should appear at the repository root. Keep the existing .gitignore. Commit the upload.
2. Create three releases/tags from that uploaded main commit:
   - ingetrazo_kitchen_maker-v1.0.2
   - make_stair-v1.1.0
   - ingetrazo_bevel-v1.0.2
   These can all point to the same commit. No ZIP release assets are necessary: the catalog uses tagged raw Python files.
3. Verify each download URL in checksums.json is reachable and its SHA-256 matches. Do not submit catalog entries before these URLs exist.
4. Submit each TOML from catalog-submissions/extensions to ingelibre/ingetrazo-extensions under extensions/. Use the matching PR text as a draft, after completing live verification. Maintainer approval is required.

## Preparation checks and limits

All three sources parse, define a top-level setup(app), fit the catalog size limit, and pass the current upstream field and artifact validator against LOCAL bytes. The validator's network fetch was replaced by the matching prepared file for this check; remote URLs have NOT been verified because tags are not published yet.

Original Python bytes and license notices are preserved. Bevel README's version was corrected from 1.0.1 to the code's 1.0.2. Documentation and examples were placed beside their plugin. The existing Kitchen Maker development/provenance disclosure is preserved. Author metadata uses the provided GitHub account.

Owner supplied 0.5.7 as the installed test version. No application runtime tests or historical automated suites were rerun during this preparation. No files have been uploaded, tags created, releases published, or pull requests opened by this preparation.
