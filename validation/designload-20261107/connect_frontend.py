from pathlib import Path
path=Path('frontend/src/main.js');text=path.read_text(encoding='utf-8')
old="weatherQualityMarkup(r.weather_quality) + '<div class=\"certificate\">"
new="weatherQualityMarkup(r.weather_quality) + designLoadsMarkup(r.metrics?.zone_design_loads) + '<div class=\"certificate\">"
assert text.count(old)==1
path.write_text(text.replace(old,new),encoding='utf-8')
