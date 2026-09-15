package demo.clean.pricing;

import java.math.BigDecimal;

public class VipPricing implements PricingStrategy {

    @Override
    public String name() {
        return "vip";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        BigDecimal discounted = base.subtract(new BigDecimal("15.00"));
        return discounted.signum() < 0 ? BigDecimal.ZERO : discounted;
    }
}
