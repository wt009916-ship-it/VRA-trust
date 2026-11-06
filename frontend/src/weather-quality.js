import {escape as esc} from './api.js';

const fieldNames = {
  dry_bulb:'干球温度',dew_point:'露点温度',horizontal_infrared:'水平长波辐射',
  extraterrestrial_horizontal_radiation:'地外水平辐射',extraterrestrial_direct_radiation:'地外法向辐射',
  global_horizontal_radiation:'总水平辐射',global_illuminance:'总水平照度',direct_illuminance:'法向直射照度',
  diffuse_illuminance:'水平散射照度',zenith_luminance:'天顶亮度',total_sky_cover:'总云量',opaque_sky_cover:'不透明云量',
  visibility:'能见度',ceiling_height:'云底高度',precipitable_water:'可降水量',aerosol_optical_depth:'气溶胶光学厚度',
  snow_depth:'积雪深度',days_since_snow:'距上次降雪天数',albedo:'地表反照率',liquid_precipitation_depth:'液态降水量',
  liquid_precipitation_quantity:'降水累计时长',present_weather_observation:'天气现象观测',present_weather_codes:'天气现象代码',
};

export function weatherQualityMarkup(quality) {
  if (!quality) return '';
  const conditions = quality.conditions || [];
  return `<section class="weather-quality" aria-label="天气输入检查"><h3>天气输入检查</h3>
    <p>${esc(quality.station?.city)} · ${esc(quality.hours)} 小时 · ${conditions.length ? '存在缺测或推导条件' : '字段筛查通过'}</p>
    <p class="subtle">${esc(quality.scope)}</p>
    <details><summary>${conditions.length ? `${conditions.length} 类缺测或推导条件，需复核` : '查看气象来源与校验范围'}</summary>
      ${conditions.length ? '<ul class="gap-list">' + conditions.map(item => `<li><strong>${esc(fieldNames[item.field] || item.field)} · ${esc(item.count)} 小时</strong><span>${esc(item.message)}（源文件第 ${esc(item.first_line)} 至 ${esc(item.last_line)} 行内，并非每行均缺测）</span></li>`).join('') + '</ul>' : ''}
      <p>应用未插补或改写原始天气。可选字段缺测不等于零，也不等于已有观测。</p>
      ${(quality.limitations || []).map(note => `<p class="subtle">${esc(note)}</p>`).join('')}
      <dl><dt>天气 SHA256</dt><dd class="mono">${esc(quality.source_sha256)}</dd><dt>校验策略</dt><dd>${esc(quality.policy_version)}</dd></dl>
    </details></section>`;
}
