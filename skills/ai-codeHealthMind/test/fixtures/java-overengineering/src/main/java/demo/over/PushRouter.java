package demo.over;

public class PushRouter implements ChannelRouter {

    @Override
    public String route(String channel) {
        return "push:" + channel;
    }
}
