"""Quick test script to verify the system works"""
import sys
sys.path.insert(0, '.')

from main import load_config
from data.fetcher import fetch_market_data, get_close_prices
from stage1.indicators import run_all_indicators
from stage1.scorer import calculate_total_score, determine_level
from stage2.rotation import calculate_all_rotations
from stage2.leading import check_all_leading
from stage2.scorer import determine_rotation_level

config = load_config()
data = fetch_market_data(period='3mo')
close = get_close_prices(data)
print(f'Data: {len(close)} rows, {len(close.columns)} tickers')
print(f'Date range: {close.index[0]} ~ {close.index[-1]}')

# Stage 1
inds = run_all_indicators(close, config['stage1'])
total = calculate_total_score(inds)
s1 = determine_level(total, config['stage1'])
print(f'\n=== STAGE 1 ===')
print(f'Total Score: {total}/10')
print(f'Level: {s1["level"]} ({s1["label"]})')
for i, ind in enumerate(inds, 1):
    print(f'  {i}. {ind["name"]}: {ind["score"]} - {ind["detail"]}')

# Stage 2
rots = calculate_all_rotations(close, config['stage2'])
leads = check_all_leading(close, config['stage2'])
s2 = determine_rotation_level(rots, leads, config['stage2'])
print(f'\n=== STAGE 2 ===')
print(f'Level: {s2["level"]} ({s2["label"]})')
print(f'Negative pairs: {s2["negative_pairs"]}/4')
for r in rots:
    c = r['change']
    cs = f'{c:+.2%}' if c is not None else 'N/A'
    print(f'  {r["label"]} ({r["pair"]}): {cs} signal={r["signal"]}')
print(f'Leading signals: {s2["leading_signals"]}/3')
for l in leads:
    c = l['change']
    cs = f'{c:+.2%}' if c is not None else 'N/A'
    print(f'  {l["label"]}: {cs} signal={l["signal"]}')

print(f'\n=== SUMMARY ===')
print(f'Stage1 Level: {s1["level"]} ({s1["label"]})')
print(f'Stage2 Level: {s2["level"]} ({s2["label"]})')
print(f'Max Level: {max(s1["level"], s2["level"])}')
print('TEST OK')
