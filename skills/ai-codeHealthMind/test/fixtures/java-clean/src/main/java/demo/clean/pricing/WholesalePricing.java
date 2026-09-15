package demo.clean.pricing;

import java.math.BigDecimal;
import java.math.RoundingMode;

public class WholesalePricing implements PricingStrategy {

    @Override
    public String name() {
        return "wholesale";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        return base.multiply(new BigDecimal("0.82")).setScale(2, RoundingMode.HALF_UP);
    }
}
