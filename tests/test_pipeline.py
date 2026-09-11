from sqlmodel import select

from netsentinel.hub.pipeline import process_batch
from netsentinel.models import Alert, Device, Event
from netsentinel.schemas import DeviceReport, DnsRecord, IngestBatch, PortReport


def test_new_device_creates_alert(session):
    batch = IngestBatch(
        sensor_id="s1",
        devices=[DeviceReport(mac="B8:27:EB:11:22:33", ip="192.168.1.50", hostname="pi-hole")],
    )
    result = process_batch(session, batch)
    session.commit()

    assert result.devices_upserted == 1
    assert result.alerts_created == 1
    dev = session.get(Device, "b8:27:eb:11:22:33")
    assert dev is not None and "Raspberry Pi" in dev.vendor
    alert = session.exec(select(Alert)).first()
    assert "New device" in alert.title and alert.severity == "medium"


def test_repeat_device_no_duplicate_alert(session):
    rep = DeviceReport(mac="B8:27:EB:11:22:33", ip="192.168.1.50")
    process_batch(session, IngestBatch(sensor_id="s1", devices=[rep]))
    session.commit()
    process_batch(session, IngestBatch(sensor_id="s1", devices=[rep]))
    session.commit()
    assert len(session.exec(select(Alert)).all()) == 1


def test_blocklisted_dns_flags_and_alerts(session):
    batch = IngestBatch(
        sensor_id="s1",
        dns=[
            DnsRecord(
                client_ip="192.168.1.10",
                qname="login.c2.evil.example",
                answer="198.51.100.7",
            )
        ],
    )
    result = process_batch(session, batch)
    session.commit()

    assert result.alerts_created >= 1
    kinds = {e.kind for e in session.exec(select(Event)).all()}
    assert "dns.flag" in kinds
    titles = " ".join(a.title for a in session.exec(select(Alert)).all())
    assert "c2.evil.example" in titles


def test_port_change_detection(session):
    first = PortReport(ip="192.168.1.20", open_ports=[22, 80])
    process_batch(session, IngestBatch(sensor_id="s1", ports=[first]))
    session.commit()

    second = PortReport(
        ip="192.168.1.20", open_ports=[22, 80, 445], services={"445/tcp": "microsoft-ds"}
    )
    result = process_batch(session, IngestBatch(sensor_id="s1", ports=[second]))
    session.commit()

    assert result.alerts_created == 1
    opened_alert = session.exec(select(Alert).where(Alert.title.contains("New open port"))).first()
    assert opened_alert is not None and "445" in opened_alert.title


def test_port_first_snapshot_is_silent(session):
    result = process_batch(
        session,
        IngestBatch(sensor_id="s1", ports=[PortReport(ip="192.168.1.20", open_ports=[22])]),
    )
    session.commit()
    assert result.alerts_created == 0
