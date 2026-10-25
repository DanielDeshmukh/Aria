/**
 * Display mirror of backend/data/orders.json for the Test orders panel.
 * Factual fields are guarded against drift by
 * backend/tests/test_frontend_orders_sync.py — edit the JSON, not this file,
 * when the mock database changes.
 */
export const ORDERS = [
  {
    id: "ORD-101",
    customer: "Priya Sharma",
    product: "Vitamin C Serum (30ml)",
    value: "₹699",
    status: "Out for Delivery",
    carrier: "BlueDart",
    tracking: "BD-982103",
    note: "Expected by 6 PM today",
  },
  {
    id: "ORD-102",
    customer: "Rahul Verma",
    product: "Hydrating Sunscreen SPF 50",
    value: "₹499",
    status: "Delivered",
    carrier: "Delhivery",
    tracking: "DL-441029",
    note: "Delivered 14 days ago · the ₹499 boundary case",
  },
  {
    id: "ORD-103",
    customer: "Ananya Patel",
    product: "Green Tea Face Wash + Toner",
    value: "₹850",
    status: "Processing",
    carrier: "—",
    tracking: "—",
    note: "Ordered 3 hours ago · eligible for cancellation",
  },
];
