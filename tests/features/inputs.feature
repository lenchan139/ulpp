@核心
Feature: 输入展开（文件夹 / zip / PDF）
  Background:
    Given 临时输入目录

  Scenario: 目录里的 PDF 被收集
    Given 临时目录里有一个 PDF "a.pdf"
    When 展开 "[dir]"
    Then 找到 1 个 PDF

  Scenario: zip 里的 PDF 被解包
    Given 打包 "box.zip" 里有 "b.pdf"
    When 展开 "box.zip"
    Then 找到 1 个 PDF

  Scenario: 非 PDF 的文件被忽略
    Given 临时目录里有一个 PDF "c.pdf"
    When 展开 "[dir]"
    Then 找到 1 个 PDF
