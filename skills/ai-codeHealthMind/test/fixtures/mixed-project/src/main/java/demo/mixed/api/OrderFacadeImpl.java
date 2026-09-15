package demo.mixed.api;

public class OrderFacadeImpl implements OrderFacade {

    @Override
    public String status(String orderId) {
        return "OPEN";
    }
}
