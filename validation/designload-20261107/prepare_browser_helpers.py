from pathlib import Path
source=Path('validation/climate-20261107');target=Path(__file__).parent
pairs=[('prepare_browser_v1.py','prepare_browser_v1.py'),('browser_driver_v1.cjs','browser_driver_v1.cjs'),
       ('browser_runtime_v2.py','browser_runtime_v1.py')]
for old,new in pairs:
 text=(source/old).read_text(encoding='utf-8').replace('windows-source-v1.json','integration-source-v1.json')
 text=text.replace('vra-weather-ui-','vra-designload-ui-').replace('weather-20261107','designload-20261107')
 text=text.replace('weather_quality_ui_test','design_load_ui_test').replace('天气输入隔离验收','分区负荷隔离验收')
 text=text.replace('browser-prepared-v2','browser-prepared-v1').replace('browser-api-v2','browser-api-v1').replace('browser-runtime-v2','browser-runtime-v1')
 with (target/new).open('x',encoding='utf-8') as stream:stream.write(text)
Path('output/playwright/designload-20261107').mkdir(parents=True,exist_ok=True)
