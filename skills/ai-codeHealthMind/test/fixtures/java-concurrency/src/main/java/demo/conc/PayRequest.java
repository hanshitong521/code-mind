package demo.conc;

public class PayRequest {

    private final String account;
    private final long amount;

    public PayRequest(String account, long amount) {
        this.account = account;
        this.amount = amount;
    }

    public String getAccount() {
        return account;
    }

    public long getAmount() {
        return amount;
    }

    public String toRow() {
        return account + ":" + amount;
    }
}
