from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At
from datetime import datetime
import asyncio
from typing import Dict, List, Tuple

# 极简账单数据结构：仅记录飞书群内消费、参与人
class SimpleAABill:
    def __init__(self, group_id: str):
        self.group_id = group_id  # 绑定飞书群ID（确保群内数据隔离）
        self.expenses: List[Tuple[str, float]] = []  # 消费记录：(付款人姓名, 金额)
        self.total_amount: float = 0.0  # 总金额
        self.members: Dict[str, str] = {}  # 参与人：{飞书用户ID: 姓名}
        self.create_time: str = datetime.now().strftime("%Y-%m-%d %H:%M")  # 账单创建时间

    def add_expense(self, payer_name: str, amount: float, payer_id: str) -> bool:
        """添加消费记录：自动更新总金额、记录参与人"""
        if amount <= 0:
            return False  # 金额必须为正数
        # 记录消费
        self.expenses.append((payer_name, round(amount, 2)))
        # 更新总金额
        self.total_amount = round(self.total_amount + amount, 2)
        # 记录付款人（飞书用户ID+姓名，避免重名）
        self.members[payer_id] = payer_name
        return True

    def calculate_aa(self) -> Tuple[float, int, float, Dict[str, float]]:
        """计算AA结果：返回（总金额, 参与人数, 每人应付金额, 收支差额）"""
        member_count = len(self.members)
        if member_count == 0:
            return (0.0, 0, 0.0, {})
        # 每人应付金额 = 总金额 / 参与人数（保留2位小数）
        per_person = round(self.total_amount / member_count, 2)
        # 统计每人已付款金额
        payer_summary: Dict[str, float] = {}
        for name, amount in self.expenses:
            payer_summary[name] = round(payer_summary.get(name, 0.0) + amount, 2)
        # 计算每人差额（已付 - 应付：正=应收回，负=应支付）
        balance = {}
        for name in self.members.values():
            paid = payer_summary.get(name, 0.0)
            balance[name] = round(paid - per_person, 2)
        return (self.total_amount, member_count, per_person, balance)

    def clear(self) -> None:
        """清空账单：重置所有数据"""
        self.expenses = []
        self.total_amount = 0.0
        self.members = {}
        self.create_time = datetime.now().strftime("%Y-%m-%d %H:%M")  # 重置创建时间


# 修复：将plugin_name改为旧版兼容的name参数
@register(
    name="astrbot_plugin_aa_simple_feishu",  # 旧版AstrBot用name，需以astrbot_plugin_开头
    author="YourName",
    description="飞书群简易AA记账：/aa 姓名 金额（记账）、/aa 对账（算AA）、/aa 清（清账）",
    version="1.0.0",
    repo_url=""  # 无需仓库可留空
)
class SimpleAASplitFeishuPlugin(Star):
    # 修复：移除旧版不支持的config参数（避免初始化报错）
    def __init__(self, context: Context):
        super().__init__(context)
        # 飞书群账单存储：{群ID: SimpleAABill对象}（确保不同群数据隔离）
        self.group_bills: Dict[str, SimpleAABill] = {}
        # 校验是否为飞书平台
        self.is_feishu = self._check_feishu()
        if self.is_feishu:
            logger.info("飞书简易AA记账插件初始化完成！")
        else:
            logger.warning("当前非飞书平台，插件仅支持飞书群使用！")

    def _check_feishu(self) -> bool:
        """校验是否为飞书平台（避免非飞书环境启动）"""
        try:
            adapter = self.context.platform_adapter
            return "feishu" in str(adapter.__class__).lower() or "feishu" in getattr(adapter, "adapter_type", "").lower()
        except Exception:
            return False

    def _get_group_bill(self, group_id: str) -> SimpleAABill:
        """获取当前飞书群的账单：不存在则创建新账单"""
        if group_id not in self.group_bills:
            self.group_bills[group_id] = SimpleAABill(group_id)
        return self.group_bills[group_id]

    # ------------------------------ 核心指令：/aa ------------------------------
    @filter.command("aa")  # 唯一主指令，通过参数区分功能
    @filter.platform_adapter_type("FEISHU")  # 仅飞书平台触发
    async def aa_main(self, event: AstrMessageEvent, *args: str):
        """飞书群简易AA记账指令
        用法1：/aa 姓名 金额 → 记录消费（如 /aa 陈 100）
        用法2：/aa 对账 → 计算AA结果
        用法3：/aa 清 → 清空当前群账单
        """
        # 1. 仅支持飞书群聊（私聊不响应）
        group_id = event.group_id
        if not group_id:
            yield event.plain_result("❌ 仅支持飞书群内使用，私聊无法记账！")
            return
        if not self.is_feishu:
            yield event.plain_result("❌ 仅飞书平台支持此插件！")
            return

        # 2. 获取当前群账单
        bill = self._get_group_bill(group_id)
        # 获取指令发送者信息（飞书用户ID+姓名）
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name() or f"用户{sender_id[-4:]}"

        # 3. 解析指令参数，区分功能
        if len(args) == 0:
            # 无参数：提示用法
            help_text = "📝 飞书简易AA记账用法：\n"
            help_text += "1. 记账：/aa 姓名 金额（如 /aa 陈 100 → 记录陈付款100）\n"
            help_text += "2. 对账：/aa 对账 → 计算总金额和每人AA金额\n"
            help_text += "3. 清账：/aa 清 → 清空当前群所有账单记录"
            yield event.plain_result(help_text)
            return

        # 功能1：/aa 清 → 清空账单
        if args[0] == "清" and len(args) == 1:
            bill.clear()
            yield event.plain_result(f"✅ 已清空当前飞书群AA账单！\n新账单创建时间：{bill.create_time}")
            logger.info(f"飞书群{group_id}（{sender_name}）清空AA账单")
            return

        # 功能2：/aa 对账 → 计算AA结果
        if args[0] == "对账" and len(args) == 1:
            # 无消费记录时提示
            if len(bill.expenses) == 0:
                yield event.plain_result("❌ 当前群暂无AA消费记录，先通过 /aa 姓名 金额 记账吧！")
                return
            # 计算AA结果
            total, member_count, per_person, balance = bill.calculate_aa()
            # 构造对账结果文本（飞书友好格式）
            result_text = f"📊 飞书群AA对账结果\n"
            result_text += f"================\n"
            result_text += f"总消费金额：¥{total:.2f}\n"
            result_text += f"参与人数：{member_count}人\n"
            result_text += f"每人应付：¥{per_person:.2f}\n\n"
            result_text += f"💸 个人收支明细：\n"
            for name, diff in balance.items():
                if diff > 0:
                    result_text += f"  {name}：多付¥{diff:.2f}（应收回）\n"
                elif diff < 0:
                    result_text += f"  {name}：少付¥{abs(diff):.2f}（应支付）\n"
                else:
                    result_text += f"  {name}：刚好付清（无差额）\n"
            # 飞书群收款提示
            result_text += f"\n📌 收款建议：\n"
            result_text += f"打开飞书群 → 点击「+」→ 选择「群收款」→ 按AA金额填写"
            yield event.plain_result(result_text)
            logger.info(f"飞书群{group_id}（{sender_name}）发起AA对账")
            return

        # 功能3：/aa 姓名 金额 → 记录消费（参数需为2个：姓名+金额）
        if len(args) == 2:
            payer_name, amount_str = args
            # 校验金额是否为数字
            try:
                amount = float(amount_str)
            except ValueError:
                yield event.plain_result(f"❌ 金额格式错误！请输入数字（如 /aa {payer_name} 100）")
                return
            # 校验金额为正数
            if amount <= 0:
                yield event.plain_result(f"❌ 金额必须为正数！请重新输入（如 /aa {payer_name} 100）")
                return
            # 添加消费记录（记录付款人飞书ID，避免重名）
            success = bill.add_expense(payer_name, amount, sender_id)
            if success:
                # 回复记账成功
                reply_text = f"✅ 记账成功！\n"
                reply_text += f"付款人：{payer_name}\n"
                reply_text += f"金额：¥{amount:.2f}\n"
                reply_text += f"当前总消费：¥{bill.total_amount:.2f}\n"
                reply_text += f"提示：输入 /aa 对账 查看AA结果，/aa 清 清空账单"
                yield event.plain_result(reply_text)
                logger.info(f"飞书群{group_id}（{sender_name}）记录AA消费：{payer_name} {amount}元")
            else:
                yield event.plain_result("❌ 记账失败！金额必须为正数")
            return

        # 其他参数情况：提示用法
        yield event.plain_result("❌ 指令格式错误！正确用法：\n1. 记账：/aa 姓名 金额（如 /aa 陈 100）\n2. 对账：/aa 对账\n3. 清账：/aa 清")

    async def terminate(self):
        """插件卸载：记录群账单状态"""
        group_count = len(self.group_bills)
        if group_count > 0:
            logger.info(f"飞书简易AA插件卸载，当前管理{group_count}个群的账单数据")
        else:
            logger.info("飞书简易AA插件卸载，无群账单数据")
