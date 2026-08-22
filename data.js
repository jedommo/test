/**
 * مؤسسة عربة الخضار التجارية
 * تم التصدير: 2026-08-22T16:46:50.538Z
 */
const initialPurchasesData = [
  {
    "id": 1,
    "date": "2026-08-22",
    "supplier": "احمد",
    "item": "كوسه",
    "quantity": 10,
    "price": 5,
    "total": 50,
    "isPaid": false,
    "paid": 30,
    "remaining": 20,
    "paymentDate": "سداد جزئي - نقدي",
    "sourceFile": "إدخال يدوي مباشر"
  }
];
const initialTransfersData = [
  {
    "id": 1787416644074,
    "date": "2026-08-22",
    "supplier": "احمد",
    "bankName": "الراجحي",
    "referenceNumber": "7676567",
    "amount": 20,
    "notes": "تحويل بنكي لتسوية حساب",
    "settledDebt": true,
    "allocations": [
      {
        "recordId": 1,
        "amount": 20
      }
    ]
  }
];
const initialCashPaymentsData = [
  {
    "id": 1787416722557,
    "date": "2026-08-22",
    "supplier": "احمد",
    "amount": 10,
    "notes": "سداد نقدي للمورد",
    "allocations": [
      {
        "recordId": 1,
        "amount": 10
      }
    ]
  }
];

if (typeof window !== 'undefined') {
  window.initialPurchasesData = initialPurchasesData;
  window.initialTransfersData = initialTransfersData;
  window.initialCashPaymentsData = initialCashPaymentsData;
}
