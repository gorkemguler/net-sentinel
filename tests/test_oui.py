from netsentinel.oui import lookup, normalise_mac


def test_normalise_mac_variants():
    assert normalise_mac("B8-27-EB-01-02-03") == "b8:27:eb:01:02:03"
    assert normalise_mac("b827eb010203") == "b8:27:eb:01:02:03"
    assert normalise_mac("B8:27:EB:01:02:03") == "b8:27:eb:01:02:03"


def test_lookup_known_vendor_from_sample():
    # b8:27:eb is the Raspberry Pi Foundation OUI, present in data/oui-sample.csv.
    assert "Raspberry Pi" in lookup("b8:27:eb:aa:bb:cc")


def test_lookup_randomised_mac_flagged():
    # Locally-administered bit set in the first octet -> randomised.
    assert lookup("b2:27:eb:aa:bb:cc") == "Randomised MAC"


def test_lookup_unknown_returns_empty():
    assert lookup("00:00:5e:00:00:01") == ""
