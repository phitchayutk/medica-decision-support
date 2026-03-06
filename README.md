# Medica Scientific Decision Support Script

Streamlit application for analyzing the Medica Scientific game export and recommending daily settings that prioritize:

- raw stockout prevention
- custom lead time protection
- queue stability across the system
- cash survivability
- endgame robustness

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Required workbook sheets

- Standard
- Custom
- Inventory
- Financial
- WorkForce

## Main outputs

- Standard Order Frequency
- Standard Order Size
- Standard S1 Allocation %
- Desired S1 Machines
- Initial Batch Size
- Manual Workday Length in Shifts
- Final Batch Size
- Standard Product Price
- S2 Allocation to First Pass %
- Desired S2 Machines
- Desired S3 Machines
- Inventory ROP
- Inventory ROQ
- Get Loan
- Pay Loan
- Desired Employees

## Notes

This is a rule-based dependency-aware controller rather than a single-metric optimizer. It uses the real export schema from the Medica Excel file and computes derived metrics, diagnostics, and recommendations on top of the workbook.
