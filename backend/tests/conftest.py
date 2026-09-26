from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

# config.py validates SumUp credentials at import — tests need valid-format dummies
os.environ.setdefault("SUMUP_API_TOKEN", "sup_sk_dummydummydummy123")
os.environ.setdefault("SUMUP_MERCHANT_CODE", "dummymerchant")
os.environ.setdefault("SUMUP_READER_ID", "rdr_dummy123")