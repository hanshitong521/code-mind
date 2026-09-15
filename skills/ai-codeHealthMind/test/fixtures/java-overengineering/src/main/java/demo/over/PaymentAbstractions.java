package demo.over;

class PaymentFactory {

    String kind() {
        return "factory";
    }
}

class PaymentProvider {

    String kind() {
        return "provider";
    }
}

class PaymentRegistry {

    String kind() {
        return "registry";
    }
}
