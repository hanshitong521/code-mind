package demo.clean.pricing;

import java.math.BigDecimal;

public class RetailPricing implements PricingStrategy {

    @Override
    public String name() {
        return "retail";
    }

    @Override
    public BigDecimal price(BigDecimal base) {
        return base;
    }
}
