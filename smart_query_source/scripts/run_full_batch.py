import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
from batch_runner import run_batch
# Explicit input files - adjust if different
input_files = [
    r'D:\BaiduNetdiskDownload\data\附件4：问题汇总.xlsx',
    r'D:\BaiduNetdiskDownload\data\附件6：问题汇总.xlsx',
]
os.makedirs('result', exist_ok=True)
run_batch(input_files, r'result\result_full_batch.xlsx', 'result')
print('BATCH_DONE')
