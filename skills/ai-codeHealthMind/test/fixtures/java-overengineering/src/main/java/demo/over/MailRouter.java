package demo.over;

public class MailRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "mail:" + channel;
    }
}
