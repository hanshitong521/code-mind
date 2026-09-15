package demo.over;

public interface OrderGateway {

    Order find(String id);

    void save(Order order);
}
