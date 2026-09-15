package demo.clean.order;

import java.time.Clock;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderMapper orderMapper;
    private final Clock clock;

    public OrderService(OrderMapper orderMapper, Clock clock) {
        this.orderMapper = orderMapper;
        this.clock = clock;
    }

    public List<OrderView> load(List<Long> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }
        List<Order> orders = orderMapper.selectBatchIds(ids);
        return orders.stream().map(this::toView).toList();
    }

    public long secondsSince(long epochMillis) {
        return (clock.millis() - epochMillis) / 1000L;
    }

    private OrderView toView(Order order) {
        return new OrderView(order.getId(), order.getAmount(), order.getStatus());
    }
}
