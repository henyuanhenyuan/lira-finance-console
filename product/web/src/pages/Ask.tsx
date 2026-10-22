import { useState } from "react";
import { Alert, Button, Collapse, Input, Space, Tag, Typography } from "antd";
import { useMutation } from "@tanstack/react-query";

import { PinRequiredError, ask } from "../api";
import { JsonBlock, Section } from "../components";
import { usePeriod } from "../period";

const suggestions = [
  "哪些商品在亏钱？",
  "A001 为什么亏？",
  "广告浪费在哪里？",
  "这个月整体怎么样？",
];

export function Ask() {
  const { range } = usePeriod();
  const [question, setQuestion] = useState("");
  const mutation = useMutation({
    mutationFn: (text: string) => ask(text, range),
  });

  const submit = () => {
    const text = question.trim();
    if (!text) return;
    mutation.mutate(text);
  };

  const result = mutation.data;
  const error =
    mutation.isError &&
    !(mutation.error instanceof PinRequiredError)
      ? (mutation.error as Error).message
      : null;

  return (
    <div className="space-y-6">
      <Section title="问一句">
        <Input.TextArea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          autoSize={{ minRows: 2, maxRows: 5 }}
          placeholder="例如：哪些商品在亏钱？A001 为什么亏？广告浪费在哪？"
        />
        <Space wrap className="mt-3">
          <Button type="primary" loading={mutation.isPending} onClick={submit}>
            提问
          </Button>
          {suggestions.map((item) => (
            <Button
              key={item}
              size="small"
              onClick={() => {
                setQuestion(item);
                mutation.mutate(item);
              }}
            >
              {item}
            </Button>
          ))}
        </Space>
        <p className="faint mt-3 text-xs">
          数字由 DuckDB 计算；本地模型只负责建议。模型不可用或建议未通过数字校验时，使用模板答案。
        </p>
      </Section>

      {error ? <Alert type="error" showIcon message={error} /> : null}

      {result ? (
        <Section
          title="回答"
          extra={
            <Space>
              <Tag>{result.intent}</Tag>
              <span className="faint text-xs">
                {result.generated
                  ? "本地模型生成建议"
                  : result.reason === "model_unavailable"
                    ? "模板（本地模型未启用）"
                    : "模板（模型建议未通过校验）"}
              </span>
            </Space>
          }
        >
          <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>
            {result.answer}
          </Typography.Paragraph>
          <Collapse
            className="mt-4"
            ghost
            items={[
              {
                key: "evidence",
                label: "查看证据",
                children: <JsonBlock value={result.evidence} />,
              },
            ]}
          />
        </Section>
      ) : null}
    </div>
  );
}
