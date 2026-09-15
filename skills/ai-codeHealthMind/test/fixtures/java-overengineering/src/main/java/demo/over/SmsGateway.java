package demo.over;

public class SmsGateway {

    public void deliver(String to, String body) throws SmsFailure {
        if (to == null || to.isBlank()) {
            throw new SmsFailure("missing destination");
        }
    }
}
