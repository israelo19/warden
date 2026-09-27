.PHONY: test proxy smoke report
test:   ; python -m pytest -q tests/
proxy:  ; python proxy/egress_proxy.py --policy policy/policy.yaml --port 3128
smoke:  ; python eval/harness.py --arm warden --trials 1
report: ; python eval/harness.py --report
