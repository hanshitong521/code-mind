package com.acme.pay;

public class PaymentClient { public String charge(String orderNo, long amountCents) { return "tx"; } public boolean refund(String transactionId, long amountCents) { return true; } }
