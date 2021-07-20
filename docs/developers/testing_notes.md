# Developer tool

## Setting up repositories

### Yubikey flow

1. `taf repo create ./law --keys-description ./data/keys.json --commit-msg "Generated initial metadata"`
2. `taf targets update-repos-from-fs ./law --library-dir ./data/targets --namespace test`
3. `taf targets generate-repositories-json ./law --library-dir ./data/targets --namespace test --custom data/custom_data.json`
4. `taf targets sign./law`
5. `taf metadata add-signing-key ./law --role targets`

### Yubikey + Keystore flow

1. `taf repo create ./law --keys-description ./data/keys.json --commit-msg "Generated initial metadata" --keystore ./data/keystore/`
1. `taf targets update-repos-from-fs ./law --library-dir ./data/targets --namespace test`
1. `taf targets generate-repositories-json ./law --library-dir ./data/targets --namespace test --custom data/custom_data.json`
1. `taf targets sign --keystore ./data/keystore/`
1. `taf metadata add-signing-key ./law --role targets`

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
