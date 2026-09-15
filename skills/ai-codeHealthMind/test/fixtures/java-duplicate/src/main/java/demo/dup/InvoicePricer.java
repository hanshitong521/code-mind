package demo.dup;

import java.math.BigDecimal;
import java.util.List;

public class InvoicePricer {

    public BigDecimal computeTotal(List<Line> lines, String region) {
        BigDecimal subtotal = BigDecimal.ZERO;
        BigDecimal tax = BigDecimal.ZERO;
        for (Line line : lines) {
            BigDecimal unit = line.getUnitPrice().multiply(BigDecimal.valueOf(line.getQuantity()));
            if (line.isTaxable()) {
                tax = tax.add(unit.multiply(new BigDecimal("0.13")));
            }
            subtotal = subtotal.add(unit);
        }
        if ("EU".equals(region)) {
            subtotal = subtotal.add(new BigDecimal("4.50"));
        } else if ("APAC".equals(region)) {
            subtotal = subtotal.add(new BigDecimal("2.25"));
        } else {
            subtotal = subtotal.add(new BigDecimal("1.00"));
        }
        BigDecimal total = subtotal.add(tax);
        if (total.signum() < 0) {
            return BigDecimal.ZERO;
        }
        return total.setScale(2, java.math.RoundingMode.HALF_UP);
    }
}
