package demo.over;

import java.util.HashMap;
import java.util.Map;

public class OrderGatewayImpl implements OrderGateway {

    private final Map<String, Order> storage = new HashMap<>();

    @Override
    public Order find(String id) {
        return storage.get(id);
    }

    @Override
    public void save(Order order) {
        storage.put(order.getId(), order);
    }
}
