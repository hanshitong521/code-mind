package demo.dup;

import java.math.BigDecimal;

public class Line {

    private final BigDecimal unitPrice;
    private final int quantity;
    private final boolean taxable;

    public Line(BigDecimal unitPrice, int quantity, boolean taxable) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.taxable = taxable;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public boolean isTaxable() {
        return taxable;
    }
}
