package demo.over;

public class SmsRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "sms:" + channel;
    }
}
