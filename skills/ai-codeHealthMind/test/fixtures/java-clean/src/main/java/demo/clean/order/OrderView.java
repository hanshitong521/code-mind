package demo.clean.order;

public class OrderView {

    private final long id;
    private final long amount;
    private final String status;

    public OrderView(long id, long amount, String status) {
        this.id = id;
        this.amount = amount;
        this.status = status;
    }

    public long getId() {
        return id;
    }

    public long getAmount() {
        return amount;
    }

    public String getStatus() {
        return status;
    }
}
