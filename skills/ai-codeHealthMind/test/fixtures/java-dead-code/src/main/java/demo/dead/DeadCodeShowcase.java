package demo.dead;

import java.util.List;

public class DeadCodeShowcase {

    private String scratchBuffer;

    public int total(List<Integer> values) {
        int sum = 0;
        for (Integer value : values) {
            sum += value;
        }
        System.out.println("total=" + sum);
        return sum;
    }

    private String computeStaleTotal(List<Integer> values) {
        StringBuilder builder = new StringBuilder();
        for (Integer value : values) {
            builder.append(value).append(',');
        }
        return builder.toString();
    }

    // TODO: delete the whole block below once the migration is finished
    /*
    private String oldFormat(Integer value) {
        String text = String.valueOf(value);
        return text.trim();
    }
    private void oldReset() {
        scratchBuffer = null;
    }
    */
}
