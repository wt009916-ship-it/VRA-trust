from pathlib import Path
p=Path('frontend/tests/agent-energy.test.js')
with p.open('a',encoding='utf-8') as f:f.write("""
test('current energy relationship is escaped and follows verified field removal', () => {
  const row = {name:'Energy',record_id:'enduse_a',facts:[],
    energy_relationship:{text:'Electricity <Gas> kWh'}};
  const markup = checkedDeliveryMarkup({checked_statements:[row]});
  assert.match(markup, /Electricity &lt;Gas&gt; kWh/);
  assert.doesNotMatch(markup, /<Gas>/);
  assert.doesNotMatch(checkedDeliveryMarkup({checked_statements:[]}), /Electricity/);
});
""")
