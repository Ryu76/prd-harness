Get-ChildItem Env: | Where-Object { $_.Name -like "*_API_KEY" } | ForEach-Object { Remove-Item Env:\$($_.Name) }
$env:PYTHONPATH="src"
python -m prd_harness --root e:\python\prd-harness\.harness --allowed-repo e:\python\prd-harness --executor "python dummy_executor.py" run-once
