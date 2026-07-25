# portable-r

This repository is the machine-readable runtime registry for **rpackit**.
Runtime archives live in platform-specific GitHub Releases; this repository
stores only version records, metadata, and schemas.

## Contract

Every published artifact has a metadata sidecar containing:

- R version, platform, and architecture;
- release URL and SHA-256 checksum;
- archive format;
- relative `R_HOME`, `Rscript`, and package-library paths.

The v1 JSON Schema is in
`schemas/portable-r-metadata-v1.schema.json`. A small standard-library Python
validator keeps registry checks independent of any package manager. It applies
the checked-in schema, verifies index/metadata consistency, enforces safe
relative runtime paths, and checks the GitHub release naming contract.

```bash
python -m unittest discover -s tests -v
python scripts/validate.py
```

The Windows 4.6.1 entry was built and relocation-tested on Windows x86_64.
Its metadata records the verified artifact checksum. The artifact is available
from the
[portable-r-windows v4.6.1 prerelease](https://github.com/rpackit/portable-r-windows/releases/tag/v4.6.1).

## Artifact naming

```text
portable-r-{platform}-{arch}-{r_version}.{zip|tar.zst|tar.gz}
```

Large runtime files must never be committed to this repository.
