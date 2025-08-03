# dotvixl
---
dotvixl (.VIXL) is an archive format like .zip or .7z, and I made it because I was bored<br>
---
### Advantages of dotvixl:
I got ChatGPT to offer some advantages that dotvixl has over other archival formats, and here they are:
- custom lightweight design
it’s built with simple structures and minimal headers, so it can be easier to parse or tweak if you want—no heavy compression schemes or complex metadata.

- built-in compression flag
.vixl supports optional zlib compression per file inside the archive, making it flexible to store compressed or uncompressed data based on your needs.

- flat, simple file table
the archive stores filenames with their offsets and sizes in a straightforward way, so your app can quickly find and extract files without complex index trees.

- small fixed header with versioning
the fixed header includes a magic number and version byte, so your parser can detect and support future updates cleanly.

---
### things that dotvixl uses to be made possible:

1. Python Standard Library (built-in)

    - sys — system functions and exit handling

    - os — operating system interfaces and file operations

    - struct — working with packed binary data

    - zlib — compression and decompression (deflate algorithm)

    - pathlib — object-oriented filesystem paths and file I/O

2. PyQt6 (GUI framework)

    - PyQt6 Official Site

    - PyQt6 on PyPI

3. Python (ofc)

    - Recommended Python version: 3.8 or higher

4. Custom Archive Format (.vixl)

    Custom archive format implemented with:

        struct (binary packing/unpacking)

        zlib (compression/decompression)

        pathlib (file system path handling)

5. Development Tools

    - pip — Python package manager

    - virtualenv — isolated Python environments
---
### An Extractor/Archiver can be downloaded in the Releases tab.
