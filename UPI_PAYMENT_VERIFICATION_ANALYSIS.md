# Automatic UPI Payment Verification for OPD Clinic Billing System

**Document Date**: May 9, 2026  
**Focus**: Practical integration for clinical environment with receptionist workflow

---

## Executive Summary

This document analyzes transitioning from manual payment confirmation (receptionist clicks "Confirm Payment Received") to **automatic verification** where the system detects payment without manual action. The analysis covers:

- **4 implementation approaches** (webhook-based, polling, hybrid, hosted)
- **6 popular Indian UPI gateways** (Razorpay, PhonePe, Google Pay for Business, Juspay, Cashfree, PayU)
- **Architecture and workflow changes** required
- **Compliance, risk, and operational considerations** for healthcare
- **Effort estimation** (complexity levels)

**Recommended Approach**: Webhook-based with Razorpay or PhonePe for clinic settings
- **Why**: Real-time verification, minimal receptionist action, built-in reconciliation
- **Implementation Effort**: Medium (3-4 weeks for a team of 2)

---

## Part 1: Current State vs. Desired State

### Current Manual Workflow

```
Patient Pays via UPI (Phone/QR Code)
       ↓
Payment Gateway Confirms
       ↓
Receptionist Checks Payment (manually)
       ↓
Receptionist Clicks "Confirm Payment Received"
       ↓
System Updates Invoice Status: PENDING → DONE
       ↓
Billing Complete
```

**Pain Points**:
1. **Delay**: Payment confirmed on gateway, but invoice not marked paid until receptionist acts
2. **Friction**: Receptionist must remember to check and click for every UPI transaction
3. **Error Prone**: Manual action may be forgotten, leading to reconciliation issues
4. **Audit Trail**: No automatic record of payment detection time
5. **Patient Experience**: No real-time confirmation visible to patient

### Desired Automatic Workflow

```
Patient Pays via UPI (Phone/QR Code)
       ↓
Payment Gateway Confirms (Razorpay/PhonePe)
       ↓
Gateway Sends Webhook to OPD System
       ↓
System Validates & Updates Invoice: PENDING → DONE (Automatic)
       ↓
Patient Sees Confirmation (SMS/Dashboard)
       ↓
Receptionist Sees Updated Status (Passive, No Action Needed)
       ↓
Billing Complete with Full Audit Trail
```

**Benefits**:
1. **Real-time**: Payment status reflects immediately
2. **Friction-less**: Zero additional receptionist action
3. **Reliable**: Automated with retry logic and reconciliation
4. **Auditable**: Every payment event logged with timestamps
5. **Patient Delight**: Instant confirmation increases satisfaction

---

## Part 2: UPI Payment Verification Approaches

### Approach A: Webhook-Based (RECOMMENDED)

**How It Works**:
1. Customer pays via QR/Dynamic Link
2. Payment succeeds on gateway
3. Gateway sends HTTP POST webhook to your server
4. Your system validates signature and updates invoice
5. Acknowledgment sent back to gateway

**Pros**:
- ✅ Real-time (milliseconds)
- ✅ Minimal server load (gateway pushes to you)
- ✅ Industry standard
- ✅ Automatic reconciliation
- ✅ Built-in retry mechanism at gateway
- ✅ Works offline (webhook queues if server unreachable)

**Cons**:
- ❌ Requires webhook endpoint (external access)
- ❌ Must validate signature (security critical)
- ❌ Network failures mean delayed processing
- ❌ Requires backlog reconciliation job

**Best For**: Clinics with stable internet, 24/7 operations

**Implementation Effort**: **Medium** (2-3 weeks)

---

### Approach B: Polling (Fallback or Standalone)

**How It Works**:
1. Customer pays via QR/Dynamic Link
2. System periodically queries gateway API for payment status (every 30-60 seconds)
3. On status match, invoice updated automatically

**Pros**:
- ✅ Simple to implement (no webhook endpoint needed)
- ✅ No signature validation complexity
- ✅ Works even if you have firewall restrictions
- ✅ Easier to debug

**Cons**:
- ❌ Delayed detection (30-60 sec latency)
- ❌ Higher API load on gateway
- ❌ Rate limits (gateways throttle polling)
- ❌ Cost per API call (some gateways charge)
- ❌ Not suitable for high-volume clinics

**Best For**: Fallback only, or low-volume clinics (<50 patients/day)

**Implementation Effort**: **Low** (1-2 weeks)

---

### Approach C: Hybrid (Webhook + Polling Fallback)

**How It Works**:
1. Primary: Webhook-based verification
2. Fallback: Polling job runs every 5 minutes
3. If webhook fails, polling catches it
4. Reconciliation job at day-end

**Pros**:
- ✅ Resilient (covers both paths)
- ✅ Real-time via webhook
- ✅ Fallback via polling
- ✅ Production-grade reliability

**Cons**:
- ❌ More complex
- ❌ Higher operational overhead
- ❌ More code to maintain

**Best For**: High-volume clinics, mission-critical billing

**Implementation Effort**: **High** (4-5 weeks)

---

### Approach D: Hosted Payment Page (Redirect)

**How It Works**:
1. Invoice created with unique order ID
2. Customer taken to gateway's hosted payment page
3. Payment confirmed on gateway
4. Customer redirected back to clinic with session token
5. System queries for payment status

**Pros**:
- ✅ PCI DSS compliant (gateway handles security)
- ✅ Works reliably in all network conditions
- ✅ Minimal webhook infrastructure needed

**Cons**:
- ❌ User experience disrupted (navigation away from app)
- ❌ Network failure = stuck customer
- ❌ Not suitable for clinic QR workflow (counter-to-patient payment)

**Best For**: Online payment links (for home delivery of reports)

**Implementation Effort**: **Low-Medium** (2-3 weeks)

---

## Part 3: Popular Indian UPI Payment Gateways

| Gateway | Webhook | Polling | Real-time Settlement | Cost (%) | Good For |
|---------|---------|---------|----------------------|----------|----------|
| **Razorpay** | ✅ Yes | ✅ Yes | 2h (T+1 settlement) | 2% | High-volume, multi-mode |
| **PhonePe Business** | ✅ Yes | ✅ Yes | Real-time/T+1 | 1.95% | High volume, lowest cost |
| **Google Pay for Business** | ⚠️ Indirect | ❌ No | T+1 | 2% | Established businesses |
| **Juspay** | ✅ Yes | ✅ Yes | Variable | 1.5-2.5% | Multi-currency, recurring |
| **Cashfree** | ✅ Yes | ✅ Yes | T+1 | 2.36% | Emerging startups |
| **PayU** | ✅ Yes | ✅ Yes | T+1 | 2% | Balanced offering |

### Detailed Gateway Comparison for Clinic Use

#### 1. **Razorpay** (Recommended for Clinics)
```
✅ Best Overall for Indian Clinics
- Industry leading (300k+ merchants)
- Excellent documentation
- Dashboard: Real-time transaction monitoring
- SDK: Node.js, Python, PHP available
- Settlement: T+1 (same-day for premium)
- Cost: 2% + 0% processing fee
- Support: 24/7 phone + email

Integration Example (Webhook):
POST /api/payment/razorpay-webhook/
Headers: X-Razorpay-Signature
Body: {
  "event": "payment.authorized",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_1234567890",
        "amount": 50000,  // In paise
        "currency": "INR",
        "receipt": "BILL-00000123",
        "vpa": "patient@upi",
        "method": "upi",
        "status": "captured"
      }
    }
  }
}
```

#### 2. **PhonePe Business** (Best Rate)
```
✅ Lowest Cost for Clinics
- 1.95% rate (industry leading)
- Real-time notifications
- Fast settlement options
- Dashboard: Good transaction history
- Settlement: T+0 (real-time) or T+1
- Cost: 1.95%
- Support: Phone + chat

Better for high-volume clinics (1000+ transactions/month)
Webhook format similar to Razorpay
```

#### 3. **Google Pay for Business** (Limited)
```
⚠️ Limited for Direct UPI
- Does not provide direct UPI webhook integration
- Primarily for consumer app integration
- Recommend Razorpay/PhonePe instead for clinic UPI
```

#### 4. **Juspay** (Best for Recurring/Subscriptions)
```
✅ Multi-currency, Recurring Payments
- Good for international patient payments
- Subscription management built-in
- Cost: 1.5-2.5% (negotiable)
- Settlement: Variable
- Complexity: Higher (more features)
```

#### 5. **Cashfree** (Growing)
```
✅ Growing Player
- Competitive 2.36% rate
- Good for startups
- Settlement: T+1
- Support: Responsive
```

#### 6. **PayU** (Balanced)
```
✅ Established Player
- 2% rate
- Multi-mode (UPI, Card, NetBanking, Wallet)
- Settlement: T+1
- Good documentation
```

---

## Part 4: Recommended Architecture

### Option 1: Webhook-Based with Razorpay (RECOMMENDED)

```
┌─────────────────────────────────────────────────────────────┐
│                    CLINIC BILLING SYSTEM                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Frontend                                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Invoice Display                                       │   │
│  │ - QR Code (Razorpay Link)                            │   │
│  │ - UPI String (upi://pay?...)                         │   │
│  │ - Amount & Bill Number                              │   │
│  └──────────────────────────────────────────────────────┘   │
│           ↓                                    ↑              │
│    (Patient Scans)                   (Status Poll Every 10s) │
│           ↓                                    ↑              │
│  Backend (Django)                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Invoice Model                                      │   │
│  │    - upi_txn_ref (payment gateway reference)         │   │
│  │    - upi_txn_id (Razorpay payment ID)               │   │
│  │    - payment_status: PENDING / CONFIRMED            │   │
│  │    - payment_method: UPI                            │   │
│  │    - paid_at: DateTime                              │   │
│  │    - webhook_received_at: DateTime                  │   │
│  │    - webhook_verified_at: DateTime                  │   │
│  │                                                      │   │
│  │ 2. PaymentWebhook Endpoint                           │   │
│  │    POST /api/payments/razorpay-webhook/             │   │
│  │    - Validate signature                             │   │
│  │    - Extract payment ID, amount, receipt (bill_id)  │   │
│  │    - Match with invoice                             │   │
│  │    - Update invoice: payment_status = CONFIRMED     │   │
│  │    - Log webhook event                              │   │
│  │    - Return 200 OK                                  │   │
│  │                                                      │   │
│  │ 3. Payment Verification Service                      │   │
│  │    verify_and_update_invoice(invoice_id)            │   │
│  │    - Check payment status via Razorpay API          │   │
│  │    - Fallback if webhook missed                     │   │
│  │                                                      │   │
│  │ 4. Reconciliation Job (Daily)                        │   │
│  │    reconcile_pending_invoices()                      │   │
│  │    - Find invoices with payment_status = PENDING    │   │
│  │    - Query Razorpay for status                      │   │
│  │    - Update if confirmed                            │   │
│  │    - Alert staff if >24h unconfirmed                │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Database                                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ BillingInvoice                                        │   │
│  │  - payment_status (PENDING, CONFIRMED)              │   │
│  │  - upi_txn_ref, upi_txn_id                          │   │
│  │  - paid_at, webhook_received_at                     │   │
│  │                                                      │   │
│  │ PaymentWebhookLog                                    │   │
│  │  - event_type, event_id, payload                    │   │
│  │  - signature_valid, processed_at                    │   │
│  │  - error_message (if failed)                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
           ↑                              ↓
           │                          Webhook POST
           │                              ↓
    Polling (Fallback)        ┌──────────────────────┐
           │                  │  RAZORPAY GATEWAY    │
           │                  │  - Payment Processing│
           └──────────────────→  - Webhook Dispatch │
                               └──────────────────────┘
```

### Database Changes

```python
# Updated BillingInvoice Model
class BillingInvoice(models.Model):
    # ... existing fields ...
    
    PAYMENT_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),          # NEW
        ("FAILED", "Failed"),                # NEW
        ("DISPUTED", "Disputed"),            # NEW
    ]
    
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default="PENDING"
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        blank=True,
        default=""
    )
    
    # Payment Gateway Fields
    upi_txn_ref = models.CharField(max_length=100, blank=True, default="")      # User-facing reference
    upi_txn_id = models.CharField(max_length=100, blank=True, default="")       # Gateway's payment ID (Razorpay: pay_xxx)
    upi_merchant_ref = models.CharField(max_length=100, blank=True, default="") # Merchant order ID
    
    # Webhook Tracking
    webhook_received_at = models.DateTimeField(null=True, blank=True)           # When webhook arrived
    webhook_verified_at = models.DateTimeField(null=True, blank=True)           # When signature verified
    webhook_processed_at = models.DateTimeField(null=True, blank=True)          # When invoice updated
    
    # Payment Timing
    paid_at = models.DateTimeField(null=True, blank=True)                       # When payment confirmed by gateway
    
    # Error Tracking
    payment_error = models.CharField(max_length=500, blank=True, default="")    # Error message if failed
    last_verification_at = models.DateTimeField(null=True, blank=True)          # Last time we checked gateway


# New Model: Payment Webhook Log
class PaymentWebhookLog(models.Model):
    EVENT_TYPES = [
        ("payment.authorized", "Payment Authorized"),
        ("payment.captured", "Payment Captured"),
        ("payment.failed", "Payment Failed"),
        ("refund.created", "Refund Created"),
    ]
    
    invoice = models.ForeignKey(BillingInvoice, on_delete=models.CASCADE, related_name="webhook_logs")
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    event_id = models.CharField(max_length=100, unique=True)                    # Razorpay event ID
    gateway_payment_id = models.CharField(max_length=100)                       # Gateway's payment ID
    
    raw_payload = models.JSONField()                                            # Full webhook payload
    signature = models.CharField(max_length=256)                                # Signature from gateway
    signature_valid = models.BooleanField(default=False)
    
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    
    received_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["invoice", "event_type"]),
            models.Index(fields=["event_id"]),
        ]
```

### Backend Implementation (Django)

```python
# settings.py - New Configuration
RAZORPAY_CONFIG = {
    'KEY_ID': os.getenv('RAZORPAY_KEY_ID'),           # Live mode
    'KEY_SECRET': os.getenv('RAZORPAY_KEY_SECRET'),
    'WEBHOOK_SECRET': os.getenv('RAZORPAY_WEBHOOK_SECRET'),
}

PAYMENT_SETTINGS = {
    'VERIFICATION_TIMEOUT': 30,      # Minutes to wait for webhook
    'FALLBACK_POLL_INTERVAL': 60,    # Seconds between polling
    'DAILY_RECONCILIATION_HOUR': 23, # Hour to run reconciliation job
    'ALERT_IF_UNCONFIRMED_HOURS': 24,
}
```

```python
# services/payment_service.py
import hmac
import hashlib
from decimal import Decimal
from django.utils import timezone
import requests
from django.conf import settings
from .models import BillingInvoice, PaymentWebhookLog

class RazorpayPaymentService:
    def __init__(self):
        self.key_id = settings.RAZORPAY_CONFIG['KEY_ID']
        self.key_secret = settings.RAZORPAY_CONFIG['KEY_SECRET']
        self.webhook_secret = settings.RAZORPAY_CONFIG['WEBHOOK_SECRET']
        self.base_url = "https://api.razorpay.com/v1"
    
    def validate_webhook_signature(self, payload, signature):
        """Validate Razorpay webhook signature."""
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)
    
    def process_webhook(self, raw_body, signature):
        """
        Process incoming webhook from Razorpay.
        1. Validate signature
        2. Parse payload
        3. Match invoice
        4. Update payment status
        """
        import json
        
        # Step 1: Validate
        if not self.validate_webhook_signature(raw_body, signature):
            return {"success": False, "error": "Invalid signature"}
        
        # Step 2: Parse
        payload = json.loads(raw_body)
        event_type = payload.get('event')
        event_id = payload.get('id')
        payment_data = payload.get('payload', {}).get('payment', {}).get('entity', {})
        
        # Step 3: Log webhook
        gateway_payment_id = payment_data.get('id')
        receipt = payment_data.get('receipt')  # Our bill_number
        
        try:
            invoice = BillingInvoice.objects.get(bill_number=receipt)
        except BillingInvoice.DoesNotExist:
            return {"success": False, "error": f"Invoice {receipt} not found"}
        
        # Log webhook
        webhook_log = PaymentWebhookLog.objects.create(
            invoice=invoice,
            event_type=event_type,
            event_id=event_id,
            gateway_payment_id=gateway_payment_id,
            raw_payload=payload,
            signature=signature,
            signature_valid=True
        )
        
        # Step 4: Process if payment.captured
        if event_type == 'payment.captured':
            payment_amount = Decimal(str(payment_data.get('amount', 0) / 100))  # Convert paise to rupees
            
            if payment_amount == invoice.total:
                invoice.payment_status = "CONFIRMED"
                invoice.payment_method = "UPI"
                invoice.upi_txn_id = gateway_payment_id
                invoice.paid_at = timezone.now()
                invoice.webhook_received_at = webhook_log.received_at
                invoice.webhook_verified_at = timezone.now()
                invoice.webhook_processed_at = timezone.now()
                invoice.save()
                
                webhook_log.processed = True
                webhook_log.processed_at = timezone.now()
                webhook_log.save()
                
                # TODO: Send notification to receptionist
                # TODO: Update patient dashboard
                # TODO: Audit log
                
                return {"success": True, "invoice_id": invoice.id}
            else:
                error = f"Amount mismatch: expected {invoice.total}, got {payment_amount}"
                webhook_log.error_message = error
                webhook_log.save()
                return {"success": False, "error": error}
        
        return {"success": True, "webhook_logged": True}
    
    def verify_payment_via_api(self, invoice_id):
        """
        Fallback: Query Razorpay API for payment status.
        Used if webhook missed or delayed.
        """
        try:
            invoice = BillingInvoice.objects.get(id=invoice_id)
        except BillingInvoice.DoesNotExist:
            return {"success": False, "error": "Invoice not found"}
        
        if not invoice.upi_merchant_ref:
            return {"success": False, "error": "No merchant reference for this invoice"}
        
        # Query Razorpay API
        url = f"{self.base_url}/orders/{invoice.upi_merchant_ref}/payments"
        auth = (self.key_id, self.key_secret)
        
        try:
            response = requests.get(url, auth=auth, timeout=10)
            if response.status_code != 200:
                return {"success": False, "error": f"API error: {response.status_code}"}
            
            payments = response.json().get('items', [])
            for payment in payments:
                if payment.get('status') == 'captured':
                    # Payment confirmed, update invoice
                    invoice.payment_status = "CONFIRMED"
                    invoice.upi_txn_id = payment.get('id')
                    invoice.paid_at = timezone.now()
                    invoice.last_verification_at = timezone.now()
                    invoice.save()
                    
                    return {"success": True, "verified": True}
            
            return {"success": True, "verified": False}
        
        except requests.RequestException as e:
            return {"success": False, "error": f"Network error: {str(e)}"}


class PaymentReconciliationService:
    """Daily reconciliation job to catch missed webhooks."""
    
    def reconcile_pending_invoices(self, max_age_hours=24):
        """
        Find invoices with payment_status=PENDING older than max_age_hours.
        Query gateway for actual status.
        """
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
        
        # Find pending invoices older than cutoff
        pending_invoices = BillingInvoice.objects.filter(
            payment_status="PENDING",
            created_at__lt=cutoff_time
        ).select_related('ledger')
        
        results = {"checked": 0, "confirmed": 0, "failed": 0, "errors": []}
        
        service = RazorpayPaymentService()
        
        for invoice in pending_invoices:
            results["checked"] += 1
            result = service.verify_payment_via_api(invoice.id)
            
            if result["success"] and result.get("verified"):
                results["confirmed"] += 1
                # TODO: Send notification to receptionist
            elif not result["success"]:
                results["failed"] += 1
                results["errors"].append({
                    "invoice_id": invoice.id,
                    "bill_number": invoice.bill_number,
                    "error": result.get("error")
                })
        
        return results
```

```python
# views/payment_views.py
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
import json
from .services import RazorpayPaymentService

@csrf_exempt  # Razorpay webhooks don't include CSRF token
@require_POST
def razorpay_webhook(request):
    """Webhook endpoint for Razorpay payment events."""
    
    try:
        raw_body = request.body.decode('utf-8')
        signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE', '')
        
        service = RazorpayPaymentService()
        result = service.process_webhook(raw_body, signature)
        
        if result.get("success"):
            return JsonResponse({"status": "ok"}, status=200)
        else:
            return JsonResponse(
                {"status": "error", "message": result.get("error")},
                status=400
            )
    
    except Exception as e:
        import logging
        logging.error(f"Webhook processing error: {str(e)}", exc_info=True)
        return JsonResponse({"status": "error"}, status=500)


@require_POST
def verify_payment(request):
    """Endpoint for frontend to check payment status."""
    
    try:
        data = json.loads(request.body)
        invoice_id = data.get('invoice_id')
        
        service = RazorpayPaymentService()
        result = service.verify_payment_via_api(invoice_id)
        
        return JsonResponse(result)
    
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
```

### Frontend Implementation

```javascript
// frontend/static/js/payment-verification.js

class PaymentVerifier {
    constructor(invoiceId, billAmount) {
        this.invoiceId = invoiceId;
        this.billAmount = billAmount;
        this.pollCount = 0;
        this.maxPolls = 60;  // 10 seconds × 60 = 10 minutes max
    }
    
    /**
     * Poll payment status every 10 seconds
     * Called after patient scans QR code
     */
    startPolling() {
        this.pollInterval = setInterval(() => {
            this.checkPaymentStatus();
        }, 10000);  // 10 seconds
    }
    
    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
    }
    
    async checkPaymentStatus() {
        this.pollCount++;
        
        if (this.pollCount > this.maxPolls) {
            this.stopPolling();
            this.onPaymentTimeout();
            return;
        }
        
        try {
            const response = await fetch('/api/payments/verify/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    invoice_id: this.invoiceId
                })
            });
            
            const result = await response.json();
            
            if (result.success && result.payment_status === 'CONFIRMED') {
                this.stopPolling();
                this.onPaymentConfirmed(result);
            }
        } catch (error) {
            console.error('Payment verification error:', error);
        }
    }
    
    onPaymentConfirmed(result) {
        // Update UI
        document.getElementById('payment-status').innerHTML = `
            <div class="alert alert-success">
                ✅ Payment Confirmed
                <br/>
                <small>Transaction ID: ${result.upi_txn_id}</small>
            </div>
        `;
        
        // Notify receptionist
        this.notifyStaff();
        
        // Update invoice display
        document.getElementById('invoice-status').textContent = 'PAID';
    }
    
    onPaymentTimeout() {
        document.getElementById('payment-status').innerHTML = `
            <div class="alert alert-warning">
                ⏱️ Payment not detected yet
                <br/>
                <small>Receptionist can still confirm manually if payment received</small>
            </div>
        `;
    }
    
    notifyStaff() {
        // TODO: WebSocket notification or Server-Sent Events
        // notify({
        //   type: 'payment_confirmed',
        //   invoice_id: this.invoiceId
        // });
    }
    
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
}

// Usage in HTML
document.addEventListener('DOMContentLoaded', () => {
    const invoiceId = document.getElementById('invoice-id').value;
    const verifier = new PaymentVerifier(invoiceId, 500.00);
    verifier.startPolling();
});
```

---

## Part 5: Implementation Timeline

### Phase 1: Foundation (Week 1-1.5)
- [ ] Set up Razorpay merchant account
- [ ] Obtain API keys and webhook secret
- [ ] Create payment gateway configuration
- [ ] Database migrations (add new fields to BillingInvoice)
- [ ] Create PaymentWebhookLog model
- [ ] Write unit tests for payment service

**Deliverable**: Payment service skeleton with signature validation

### Phase 2: Webhook Implementation (Week 2)
- [ ] Implement webhook endpoint
- [ ] Test webhook payload parsing
- [ ] Integrate with BillingInvoice update
- [ ] Create audit logging
- [ ] Test signature validation
- [ ] Implement error handling

**Deliverable**: Webhook endpoint accepting and processing payments

### Phase 3: Fallback & Reconciliation (Week 2.5)
- [ ] Implement API-based verification
- [ ] Create polling mechanism (for fallback)
- [ ] Write daily reconciliation job
- [ ] Create Celery/APScheduler task for reconciliation
- [ ] Alert mechanism for unconfirmed invoices

**Deliverable**: Resilient payment verification system

### Phase 4: Frontend & Integration (Week 3)
- [ ] Frontend polling logic
- [ ] Real-time status updates
- [ ] Receptionist dashboard changes
- [ ] Patient notification (SMS/email)
- [ ] Invoice PDF generation with payment status

**Deliverable**: Full patient-to-receptionist workflow

### Phase 5: Testing & Deployment (Week 3.5-4)
- [ ] Integration testing
- [ ] UAT with receptionist users
- [ ] Load testing (simulate concurrent payments)
- [ ] Webhook delivery testing
- [ ] Security review
- [ ] Production deployment

**Deliverable**: Tested, production-ready system

---

## Part 6: Compliance & Regulatory Considerations

### India-Specific Healthcare Compliance

#### 1. **Billing & Audit Requirements** (RBI, GST)
- ✅ Invoice generation: Already in place (BILL-xxxxxxxx)
- ✅ Payment audit trail: PaymentWebhookLog captures all events
- ✅ Reconciliation: Daily job ensures all payments recorded
- ⚠️ **Action**: Ensure Daily Reconciliation Reports generated for compliance

#### 2. **GST Compliance**
- ✅ Current system: BillingInvoice.tax field exists
- ✅ UPI Payment: No impact on GST calculation
- ⚠️ **Action**: Ensure payment method (UPI) recorded for GST filings

#### 3. **Data Protection** (HIPAA-equivalent in India = Local privacy laws)
- ⚠️ **Consider**: Do not log full UPI IDs in plaintext
- ✅ **Implement**: Hash sensitive payment references
- ⚠️ **Action**: Implement data encryption for upi_txn_id

#### 4. **PCI DSS Compliance** (Payment Card Industry)
- ✅ Using Razorpay: Clinic never touches raw payment data
- ✅ Clinic systems: No card/bank data stored
- ⚠️ **Action**: Verify Razorpay's PCI DSS certification (they handle it)

#### 5. **RBI Guidelines for Payment Systems**
- ✅ UPI: NPCI-regulated, reliable
- ✅ Payment limits: No impact from system (gateway enforces)
- ⚠️ **Action**: Monitor daily transaction caps (currently ₹100,000/day typical)

#### 6. **Invoice & Billing Records**
- ✅ Retention: Keep webhook logs for 7 years (regulatory)
- ⚠️ **Action**: Archive old PaymentWebhookLog records

### Checklist

```
Healthcare Compliance Checklist for Auto-UPI Payment
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☐ GST Compliance: Payment method recorded in invoice
☐ Audit Trail: PaymentWebhookLog captures all events
☐ Data Protection: Payment IDs hashed/encrypted
☐ PCI DSS: Using Razorpay (no direct card handling)
☐ RBI Compliance: Daily transaction monitoring
☐ Record Retention: 7-year archival policy
☐ Dispute Resolution: Process documented
☐ Staff Training: Receptionist trained on new workflow
☐ Error Handling: Procedure for failed payments
☐ Patient Notification: SMS/email confirmation sent
```

---

## Part 7: Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Webhook Failure (Network) | Payment not confirmed | High | Fallback polling job + reconciliation |
| Signature Validation Fails | Security breach possible | Low | Test signatures, use hmac.compare_digest() |
| Amount Mismatch | Patient pays wrong amount | Medium | API query on webhook, validate amount |
| Duplicate Processing | Patient charged twice | Medium | Idempotency check (event_id unique) |
| Delayed Webhook (>1h) | Reconciliation catches it | Medium | Daily job + alert if >24h unconfirmed |
| Gateway Downtime | Cannot accept payments | Low | QR codes cached locally, manual confirmation fallback |
| Rate Limit (API Polling) | Verification slow | Low | Limit polling to <5/min per invoice |
| Regulatory Audit | Payment method not documented | Low | PaymentWebhookLog audit trail |
| Patient Notification Failure | No SMS sent | Medium | Fallback email + dashboard display |

---

## Part 8: Operational Considerations

### Receptionist Workflow Changes

#### Before (Manual)
```
1. Patient pays via UPI
2. Receptionist checks Razorpay dashboard
3. Receptionist manually clicks "Confirm Payment"
4. Invoice status updates
5. Receptionist prints receipt
Average Time: 2-3 minutes
```

#### After (Automatic)
```
1. Patient pays via UPI
2. System detects payment (webhook or polling)
3. Invoice status updates automatically
4. Receptionist sees green checkmark on screen
5. Receptionist prints receipt
Average Time: <10 seconds + webhook delay
```

**Receptionist Training**:
- ✅ No action required for successful UPI payments
- ⚠️ Manual confirm still available for edge cases
- ✅ Dashboard shows real-time payment status
- ✅ Daily reconciliation report shows any gaps

### Monitoring & Alerting

```
Metrics to Monitor:
1. Webhook Success Rate: >99%
2. Payment Confirmation Latency: <5 seconds (median)
3. Daily Unconfirmed Payments: 0 by end of day
4. Webhook Signature Validation: 100%
5. Duplicate Event Detection: 0 successful duplicates
6. API Rate Limit Hits: 0

Alerts:
- Webhook endpoint down: Page on-call engineer
- >10% webhook failures in 1 hour: Page on-call engineer
- Unconfirmed invoices >24h: Email clinic manager daily
- Webhook processing lag >5min: Email clinic manager
```

### Rollback Plan

If automatic system fails:
1. Disable webhook endpoint (manual confirmation remains functional)
2. All invoices fall back to manual confirmation
3. Polling continues in background
4. Daily reconciliation catches any payments

**Time to Rollback**: <5 minutes
**Data Loss**: None (all payments still recorded)

---

## Part 9: Cost Estimation

### Gateway Costs

| Item | Cost | Notes |
|------|------|-------|
| Razorpay 2% | 2% × ₹20,000/month = ₹400 | 100 invoices × ₹200 avg |
| PhonePe 1.95% | 1.95% × ₹20,000/month = ₹390 | Slightly cheaper |
| Monthly Settlement | ₹0 | Razorpay T+1 included |
| API Calls (100/month) | ₹0 | Free tier includes |

### Development Costs

| Task | Hours | Team | Cost |
|------|-------|------|------|
| Backend (Django) | 40-50 | 1 Dev | $400-500 |
| Frontend (JS) | 15-20 | 1 Dev | $150-200 |
| Testing & QA | 20-25 | 1 QA | $150-200 |
| Deployment & Ops | 10 | 1 DevOps | $100 |
| **Total** | **85-105** | **2 people** | **$800-1000** |

**Implementation Timeline**: 3-4 weeks (with 2-person team)

---

## Part 10: Go/No-Go Decision Framework

### Go Conditions ✅

- [x] Team has bandwidth (2 people, 3-4 weeks)
- [x] Razorpay account active with test keys
- [x] Current manual system working
- [x] Receptionist buy-in (workflow improves)
- [x] Compliance review cleared
- [x] Database backup strategy in place

### No-Go Conditions ❌

- ❌ Current billing system unstable
- ❌ No internet backup at clinic (required for webhooks)
- ❌ Regulatory concerns unresolved
- ❌ Team bandwidth unavailable

---

## Recommendations

### For Your OPD Clinic (Small to Medium)

**Implementation Approach**: **Webhook + Polling (Hybrid)**

**Why**:
1. **Reliable**: Catches missed webhooks with polling fallback
2. **Fast**: Real-time via webhook
3. **Practical**: Works in clinic environment with intermittent connectivity
4. **Manageable**: Not overly complex for your team

**Gateway Choice**: **Razorpay**

**Why**:
1. **Proven**: 300k+ merchants, trusted
2. **Clinic-Friendly**: Good documentation, 24/7 support
3. **Cost**: 2% is market standard
4. **Ecosystem**: Integrates well with Python/Django

**Timeline**: **4 weeks**
- Week 1: Database + Payment Service
- Week 2: Webhook endpoint
- Week 3: Frontend + Polling
- Week 4: Testing + Deployment

**Next Steps**:
1. ✅ Get this analysis reviewed by tech lead
2. ✅ Validate with receptionist users
3. ✅ Create Razorpay merchant account (if not done)
4. ✅ Begin Phase 1 implementation

---

## Appendices

### A. Razorpay Webhook Event Examples

```json
{
  "event": "payment.captured",
  "created_at": 1715251200,
  "id": "evt_xxxxxxxxxxxx",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_1A2B3C4D5E6F7G",
        "entity": "payment",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "receipt": "BILL-00000123",
        "email": "patient@example.com",
        "contact": "+919876543210",
        "vpa": "patient@upi",
        "description": null,
        "amount_refunded": 0,
        "refund_status": null,
        "captured": true,
        "dispute": false,
        "fee": 1000,
        "tax": 0,
        "notes": [],
        "fee_details": null,
        "acquirer_data": {
          "rrn": "318750193117"
        },
        "created_at": 1715251195
      }
    }
  }
}
```

### B. Polling Implementation (Fallback)

```python
# Celery task for fallback polling
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task
def poll_unconfirmed_payments():
    """
    Fallback polling: Every 5 minutes, check unconfirmed invoices.
    Used if webhook mechanism fails.
    """
    cutoff = timezone.now() - timedelta(minutes=5)
    
    unconfirmed = BillingInvoice.objects.filter(
        payment_status="PENDING",
        payment_method="UPI",
        created_at__gt=cutoff
    )
    
    service = RazorpayPaymentService()
    results = {"checked": 0, "confirmed": 0}
    
    for invoice in unconfirmed:
        result = service.verify_payment_via_api(invoice.id)
        results["checked"] += 1
        if result.get("verified"):
            results["confirmed"] += 1
    
    return results
```

### C. Database Indexes to Add

```python
# Add to BillingInvoice Meta class
class Meta:
    indexes = [
        models.Index(fields=["payment_status"]),
        models.Index(fields=["upi_txn_id"]),
        models.Index(fields=["created_at", "payment_status"]),
    ]
```

### D. Testing: Local Webhook Simulation

```python
# For testing without live Razorpay
def test_webhook_signature_validation():
    from .services import RazorpayPaymentService
    import json
    import hmac
    import hashlib
    
    service = RazorpayPaymentService()
    webhook_secret = "test_secret"
    
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "amount": 50000,
                    "receipt": "BILL-00000123",
                    "status": "captured"
                }
            }
        }
    }
    
    payload_json = json.dumps(payload)
    signature = hmac.new(
        webhook_secret.encode(),
        payload_json.encode(),
        hashlib.sha256
    ).hexdigest()
    
    result = service.process_webhook(payload_json, signature)
    assert result["success"] == True
```

---

## Summary Table: Decision Matrix

| Factor | Manual | Polling Only | Webhook Only | Webhook + Polling |
|--------|--------|--------------|--------------|-------------------|
| Real-time | ❌ Slow | ❌ Slow (30s) | ✅ Fast (<1s) | ✅ Fast (<1s) |
| Reliability | ⚠️ Human dependent | ⚠️ Rate limited | ⚠️ Network failure | ✅ Resilient |
| Complexity | ✅ Simple | ⚠️ Medium | ⚠️ Medium | ⚠️ High |
| Cost | ⚠️ Staff time | ⚠️ API calls | ✅ Minimal | ⚠️ Polling overhead |
| **Recommendation** | Current | **Not ideal** | **Good** | **BEST** |

**Recommended**: **Webhook + Polling (Hybrid)** for clinic environment

---

**Document Version**: 1.0  
**Last Updated**: May 9, 2026  
**Author**: AI Assistant  
**Status**: Ready for Implementation Review
