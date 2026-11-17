@核心
Feature: 校准向导的放纸结论
  Scenario Outline: 两个答案推出放纸方向
    Given 答案是 face "<face>" edge "<edge>"
    Then feed 是 "<feed>"

    Examples:
      | face | edge  | feed           |
      | up   | short | face_up_short  |
      | up   | long  | face_up_long   |
      | down | short | face_down_short|
      | down | long  | face_down_long |
      | none | short | fallback       |
      | up   | none  | fallback       |
