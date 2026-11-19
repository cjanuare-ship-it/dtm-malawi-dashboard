# DTM Malawi · RE2CLID GIS Workspace (prototype)

Interactive GIS workspace for the IOM Displacement Tracking Matrix (DTM) Malawi, RE2CLID programme.
The site is a single self-contained `index.html`, **encrypted with [StatiCrypt](https://github.com/robinmoisson/staticrypt)**: the
repository only holds encrypted data, and the page decrypts in the browser after the site password is entered.

## Access levels
1. **Site password**: required for everyone (protects the data on this public repository).
2. **Welcome screen**:
   - *Viewer*: read-only, no further password.
   - *Technician*: technician password; can add and style layers, build the report and prepare updates.

## Updating the published site
1. Sign in as a technician, make the changes, press **Publish → Download site file for a server** (gives an unencrypted `index.html`).
2. Encrypt it on your computer (Node.js required). Never upload the unencrypted file to this public repository:
   ```
   npx staticrypt index.html -p "<site password>" --short --remember 30 -d encrypted
   ```
3. Upload `encrypted/index.html` into this `gis/` folder (Add file → Upload files), replacing `index.html`. GitHub Pages updates within a minute or two.

Boundaries: OCHA COD-AB Malawi 2023 · Basemap: Natural Earth · Prototype — for illustration only. The boundaries and names shown and the
designations used do not imply official endorsement or acceptance by IOM.
