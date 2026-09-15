package demo.over;

public class NotificationSender {

    private final SmsGateway gateway;

    public NotificationSender(SmsGateway gateway) {
        this.gateway = gateway;
    }

    public void send(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms delivery failed for " + to, ex);
        }
    }

    public void resend(String to, String body) {
        try {
            gateway.deliver(to, body);
        } catch (SmsFailure ex) {
            throw new IllegalStateException("sms retry failed for " + to, ex);
        }
    }
}
