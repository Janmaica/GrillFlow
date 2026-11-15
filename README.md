# 🔥 GrillFlow

**An Offline-First Barbecue Business Management Application**

GrillFlow is a Python-based business management application designed to help small barbecue business owners manage daily operations, track sales, monitor customer credit (_utang_), record expenses, and review business performance.

The application aims to provide a simple, user-friendly interface with understandable financial information, making business management more accessible to owners without extensive accounting knowledge.

## Project Status

**In Development — Stage 1: Application Foundation**

The initial Kivy application has been created and successfully tested on Windows. Core business features are currently under development.

## Technologies

- **Python 3.11** — Primary programming language
- **Kivy 2.3.2** — Cross-platform UI framework
- **SQLite** — Planned offline database
- **Git & GitHub** — Version control
- **VS Code** — Development environment

**Target Platform:** Android

## Planned Features

### Dashboard

- Daily, weekly, and monthly business summaries
- Total sales, cash collected, outstanding credit, and expenses
- Estimated earnings and possible loss indicators
- Tappable financial cards with simple Cebuano explanations displayed in bottom sheets

### Sales and Order Management

- Create orders with multiple products and quantities
- Automatically generated customer names (Unknown1, Unknown2, etc.)
- Track order preparation: Pending, Cooking, Ready, and Received
- Track payments: Unpaid, Partially Paid, and Paid
- Automatically calculate cash change (_sukli_)
- Review active orders and completed transactions

### Products

- Add, edit, and archive products
- Set product names and selling prices
- Track product quantities and availability

### Customer Credit (Utang)

- Record credit transactions under named customers
- View individual orders, items, quantities, dates, and times
- Track outstanding balances and payment status
- Record partial and full payments
- Maintain customer payment history

### Receipts

- Generate itemized receipts for customer orders
- Display product names, quantities, unit prices, and totals
- Show cash received, change, and remaining balance
- Preview, print, or share receipts

### Expenses

- Record business purchases and operating expenses
- Categorize expenses such as meat, marinade, charcoal, and transportation
- Review expenses by date

### Family Consumption

- Record barbecue products consumed by family members
- Deduct consumed quantities from available inventory
- Keep family consumption separate from customer sales
- Display quantities and retail values without treating them as actual sales or exact losses

### Financial Reports

- Daily, weekly, and monthly summaries
- Sales and cash collection reports
- Expense and outstanding credit reports
- Estimated earnings and possible loss indicators
- Clear distinctions between sales, cash flow, and accounting profit

## Application Navigation

The five primary navigation destinations are:

**Home | Sales | Products | Utang | Reports**

Additional features, including Expenses, Family Consumption, Inventory, and Settings, will be accessible through secondary navigation.

## Development Roadmap

- [x] Create GitHub repository
- [x] Configure Python virtual environment
- [x] Install and verify Kivy
- [x] Create and test initial application window
- [ ] Implement application navigation and orange-themed screens
- [ ] Implement SQLite database
- [ ] Develop product and order management
- [ ] Implement payments, credit tracking, and receipts
- [ ] Implement expenses and family consumption
- [ ] Develop financial reports
- [ ] Test and package Android APK

## Running the Current Prototype

Clone the repository:

```bash
git clone https://github.com/Janmaica/GrillFlow.git
cd GrillFlow
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```cmd
.venv\Scripts\activate
```

Install Kivy:

```bash
python -m pip install kivy==2.3.2
```

Run the application:

```bash
python main.py
```

**Note:** The current version is a Windows-tested Kivy prototype. Android APK packaging has not yet been completed.

## Project Goals

GrillFlow aims to simplify everyday barbecue business management by providing offline access to sales records, order preparation, customer credit, receipts, expenses, family consumption, and understandable financial summaries.

---

**GrillFlow — Manage Every Sale. Track Every Peso.**
