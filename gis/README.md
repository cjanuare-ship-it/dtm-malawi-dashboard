# DTM Malawi · RE2CLID GIS Workspace (prototype)

Interactive GIS workspace for the IOM Displacement Tracking Matrix (DTM) Malawi, RE2CLID programme.
The site is a single self-contained `index.html`, **encrypted with [StatiCrypt](https://github.com/robinmoisson/staticrypt)**: the
repository only holds encrypted data, and the page decrypts in the browser after the site password is entered.

## Access levels
1. **Site password**: required for everyone (protects the data on this public repository).
2. **Welcome screen**:
   - *Viewer*: read-only, no further password.
   - *Technician*: technician password; can add and style layers, build the report and prepare updates.

## Updating the published site (technicians)
1. Open the site, enter the site password, choose **Technician** and sign in.
2. Make the changes, then press **Publish → Publish to the live site on GitHub**.
3. Enter the **site password** and a **GitHub fine-grained token** (first time only):
   GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token →
   *Only select repositories*: this repository → Repository permissions → **Contents: Read and write** → set an expiry → Generate.
4. The page encrypts the new version in the browser and commits it here. GitHub Pages updates the site for viewers in about a minute.

The unencrypted site file (Publish → Download the site file) is for other servers only. Never upload it to this public repository.

Boundaries: OCHA COD-AB Malawi 2023 · Basemap: Natural Earth · Prototype — for illustration only. The boundaries and names shown and the
designations used do not imply official endorsement or acceptance by IOM.
