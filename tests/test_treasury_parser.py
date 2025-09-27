
import datetime as dt
from quantdesk.data.ingest.treasury import _parse_month_xml

SAMPLE_XML = """<?xml version='1.0' encoding='utf-8'?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry>
    <content type="application/xml">
      <m:properties>
        <d:NEW_DATE>2025-08-01T00:00:00</d:NEW_DATE>
        <d:BC_10YEAR>3.40</d:BC_10YEAR>
        <d:BC_1_5MONTH>4.41</d:BC_1_5MONTH>
      </m:properties>
    </content>
  </entry>
</feed>"""

def test_parse_month_xml():
    rows=_parse_month_xml(SAMPLE_XML)
    assert len(rows)==1
    r=rows[0]
    assert r["date"]==dt.date(2025,8,1)
    assert r["BC_10YEAR"]==3.40
    assert r["BC_1_5MONTH"]==4.41
