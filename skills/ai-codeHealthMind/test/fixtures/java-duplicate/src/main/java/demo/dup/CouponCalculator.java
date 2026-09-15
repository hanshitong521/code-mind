package demo.dup;

import java.math.BigDecimal;
import java.util.List;

public class CouponCalculator {

    public BigDecimal couponValue(List<String> codes, BigDecimal paid) {
        if (codes == null || codes.isEmpty()) {
            return BigDecimal.ZERO;
        }
        BigDecimal best = codes.stream()
                .map(code -> BigDecimal.valueOf(code.length()))
                .reduce(BigDecimal.ZERO, BigDecimal::max);
        BigDecimal capped = best.min(paid);
        return capped.max(BigDecimal.ZERO);
    }
}
