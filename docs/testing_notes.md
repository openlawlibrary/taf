# Developer tool

## Setting up repositories

### Yubikey flow

1. `taf create_repo --repo-path ./law --keys-description ./data/keys.json --commit-msg "Generated initial metadata"`
1. `taf update_repos_from_fs --repo-path ./law --targets-dir ./data/targets --namespace test`
1. `taf generate_repositories_json --repo-path ./law --targets-dir ./data/targets --namespace test --custom data/custom_data.json`
1. `taf sign_targets --repo-path ./law`
1. `taf add_signing_key --repo-path ./law --role targets`

### Yubikey + Keystore flow

1. `taf create_repo --repo-path ./law --keys-description ./data/keys.json --commit-msg "Generated initial metadata" --keystore ./data/keystore/`
1. `taf update_repos_from_fs --repo-path ./law --targets-dir ./data/targets --namespace test`
1. `taf generate_repositories_json --repo-path ./law --targets-dir ./data/targets --namespace test --custom data/custom_data.json`
1. `taf sign_targets --repo-path ./law --keystore ./data/keystore/`
1. `taf add_signing_key --repo-path ./law --role targets`

### keys.json

```
{
    "roles": {
        "root": {
          "yubikey": true,
          "number": 3,
          "length": 2048,
          "threshold": 2
        },
        "targets": {
           "yubikey": true,
           "length": 2048
        },
        "snapshot": {},
        "timestamp": {}
    }
}
```

### custom_data.json

```
{
    "test/law-xml": {
        "type": "xml",
        "allow-unauthenticated-commits": true
    },
    "test/law-xml-codified": {
        "type": "xml-codified"
    },
    "test/law-html": {
        "type": "html"
    }
}
```
