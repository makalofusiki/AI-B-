import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from batch_runner import run_batch
# Use SQLite database in data directory
input_files = [
    r'D:\BaiduNetdiskDownload\data\smart_query_assistant\data\financial_reports.sqlite',
]
os.makedirs('result', exist_ok=True)
run_batch(input_files, r'result\result_full_batch.xlsx', 'result')
print('BATCH_DONE')