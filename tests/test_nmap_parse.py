from netsentinel.sensor.collectors.port_scan import parse_nmap_xml

SAMPLE_XML = """<?xml version="1.0"?>
<nmaprun scanner="nmap">
  <host>
    <status state="up"/>
    <address addr="192.168.1.10" addrtype="ipv4"/>
    <address addr="B8:27:EB:AA:BB:CC" addrtype="mac" vendor="Raspberry Pi"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="9.2p1"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="closed"/>
        <service name="http"/>
      </port>
      <port protocol="tcp" portid="8080">
        <state state="open"/>
        <service name="http-proxy"/>
      </port>
    </ports>
  </host>
  <host>
    <status state="down"/>
    <address addr="192.168.1.11" addrtype="ipv4"/>
  </host>
</nmaprun>
"""


def test_parse_extracts_open_ports_only():
    reports = parse_nmap_xml(SAMPLE_XML)
    assert len(reports) == 1  # the "down" host is skipped
    r = reports[0]
    assert r.ip == "192.168.1.10"
    assert r.mac == "b8:27:eb:aa:bb:cc"
    assert r.open_ports == [22, 8080]
    assert "OpenSSH" in r.services["22/tcp"]


def test_parse_bad_xml_is_safe():
    assert parse_nmap_xml("not xml at all") == []
