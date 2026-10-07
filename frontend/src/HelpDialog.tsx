import { useEffect, useRef } from "react";

export default function HelpDialog({ onClose }: { onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="help-dialog"
      aria-labelledby="help-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="help-heading">
        <div>
          <span className="section-kicker">随时查阅</span>
          <h2 id="help-title">使用帮助</h2>
        </div>
        <button onClick={onClose} aria-label="关闭使用帮助">
          ✕
        </button>
      </div>
      <div className="help-sections">
        <section>
          <h3>怎样开始备课？</h3>
          <p>
            点击左侧“新建备课”，输入会话名称后，在底部输入主题、年级、时长和重点。输入框右侧可选择备课模式；信息不足时，系统会继续提问。左侧可以新建和切换会话。
          </p>
          <p>
            在输入框上方勾选要生成的材料，可同时选择 PPT 课件、Word
            教案、教学提纲和互动内容。需求已说明清楚时，可以回复“开始生成”跳过追问。
          </p>
        </section>
        <section>
          <h3>需要先上传资料吗？</h3>
          <p>
            不需要。直接描述需求也可以生成。资料只用于所属会话，在知识库中可以删除；删除资料不会移除已生成的课件。
          </p>
          <p>
            每个会话都可上传和保存资料，点击右上角“知识库”打开资料侧栏即可上传。开启“使用参考资料”，再到知识库勾选本次要用的文件；只参考勾选文件，关闭时不引用上传资料。可上传
            PDF、Word（.docx）、PPT（.pptx）、图片、视频和录音。
          </p>
        </section>
        <section>
          <h3>材料生成后在哪里？</h3>
          <p>
            打开右侧“产物预览”，下载 PPT 和 Word
            教案，也可以生成试卷或互动内容。要修改某一份材料，选择“课件”或“教案”，再输入修改意见。
          </p>
        </section>
        <section>
          <h3>语音、资料与保存</h3>
          <p>语音输入由浏览器提供</p>
          <p>
            使用前需允许麦克风权限，识别支持取决于浏览器。上传录音目前使用演示转写；扫描版
            PDF 不保证识别文字。DeepSeek
            模式下，文字与图片使用真实模型，知识库使用本地文本检索。
          </p>
          <p>
            备课会话保存在当前浏览器。刷新会恢复记录；更换浏览器或清除网站数据后，不会自动同步。删除会话会同时移除该会话的资料和生成文件。重要材料请及时下载。
          </p>
        </section>
      </div>
      <button className="help-done" onClick={onClose}>
        知道了，开始备课
      </button>
    </dialog>
  );
}
