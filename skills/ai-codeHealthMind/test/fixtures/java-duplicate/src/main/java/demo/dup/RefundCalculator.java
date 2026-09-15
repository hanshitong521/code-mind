package demo.dup;

import java.math.BigDecimal;

public class RefundCalculator {

    public BigDecimal refundFor(String reasonCode, BigDecimal paid, int daysHeld) {
        switch (reasonCode) {
            case "DAMAGED":
                return paid;
            case "LATE":
                int remaining = daysHeld;
                BigDecimal amount = paid;
                while (remaining > 0) {
                    amount = amount.multiply(new BigDecimal("0.90"));
                    remaining--;
                }
                return amount;
            default:
                return BigDecimal.ZERO;
        }
    }
}
