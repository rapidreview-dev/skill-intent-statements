"""The entry point: a pull request comes in, is billed and reviewed."""
from credits import bill_review


def run_review(files):
    return f"reviewed {files} files"


def review(account, files):
    bill_review(account, files)
    return run_review(files)
