package demo.clean.sdk;

import com.acme.pay.PaymentClient;
import org.springframework.stereotype.Component;

@Component
public class PaymentSdkAdapter {

    private final PaymentClient client;

    public PaymentSdkAdapter(PaymentClient client) {
        this.client = client;
    }

    public String charge(String orderNo, long amountCents) {
        return client.charge(orderNo, amountCents);
    }

    public boolean refund(String transactionId, long amountCents) {
        return client.refund(transactionId, amountCents);
    }
}
