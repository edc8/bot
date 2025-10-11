from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger  # 使用 astrbot 提供的 logger 接口

@register("aabill", "author", "一个支持记账、查账、对账和删除账单的 AA 分账插件", "1.1.0", "repo url")
class AABillPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.bills = {}  # 用于存储账目，格式为 {"名字": 金额}

    @filter.command("记账")
    async def record_bill(self, event: AstrMessageEvent):
        """
        指令：/记账 <名字> <金额>
        记录某人的支出金额
        """
        user_name = event.get_sender_name()  # 获取用户昵称
        message_str = event.message_str.strip()  # 获取并处理指令内容
        
        logger.info(f"用户 {user_name} 调用了记账指令: {message_str}")
        
        # 指令解析
        try:
            parts = message_str.split()
            name = parts[0]
            amount = float(parts[1])
        except (IndexError, ValueError):
            yield event.plain_result("格式错误！正确的格式是 `/记账 <名字> <金额>`。例如：`/记账 陈 100`")
            return
        
        if name not in self.bills:
            self.bills[name] = 0
        self.bills[name] += amount

        yield event.plain_result(f"已记录{name}的支出：{amount:.2f}元！当前总支出为：{sum(self.bills.values()):.2f}元")

    @filter.command("查账")
    async def check_bill(self, event: AstrMessageEvent):
        """
        指令：/查账
        列出所有的记账记录
        """
        logger.info("用户调用了查账指令。")
        
        if not self.bills:
            yield event.plain_result("目前没有记账记录！")
            return
        
        total = sum(self.bills.values())
        bill_details = "\n".join([f"{name}: {amount:.2f} 元" for name, amount in self.bills.items()])
        
        result = f"当前账目：\n{bill_details}\n\n总支出：{total:.2f} 元"
        yield event.plain_result(result)

    @filter.command("对账")
    async def settle_bill(self, event: AstrMessageEvent):
        """
        指令：/对账
        计算每人的分摊金额，以及谁需要补钱/收钱
        """
        logger.info("用户调用了对账指令。")
        
        if not self.bills:
            yield event.plain_result("目前没有记账记录，无法进行对账！")
            return
        
        total = sum(self.bills.values())
        num_people = len(self.bills)
        average = total / num_people

        adjustments = {name: amount - average for name, amount in self.bills.items()}
        owe_list = []
        receive_list = []

        for name, balance in adjustments.items():
            if balance > 0:
                receive_list.append(f"{name} 应收 {balance:.2f} 元")
            elif balance < 0:
                owe_list.append(f"{name} 需补 {-balance:.2f} 元")
        
        result = f"总支出：{total:.2f} 元\n均摊后每人应支付：{average:.2f} 元\n\n以下是对账详情：\n\n"
        if receive_list:
            result += "应收款项：\n" + "\n".join(receive_list) + "\n"
        if owe_list:
            result += "需付款项：\n" + "\n".join(owe_list) + "\n"

        yield event.plain_result(result)

    @filter.command("删除账单")
    async def delete_bill(self, event: AstrMessageEvent):
        """
        指令：/删除账单 <名字>
        删除某个人的账单记录
        """
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()
        
        logger.info(f"用户 {user_name} 调用了删除账单指令: {message_str}")
        
        if not message_str:
            yield event.plain_result("请提供需要删除账单的姓名，格式为 `/删除账单 <名字>`")
            return
        
        name = message_str.split()[0]
        if name in self.bills:
            del self.bills[name]
            yield event.plain_result(f"已删除{name}的账单记录。")
        else:
            yield event.plain_result(f"没有找到名字为{name}的账单记录。")

    async def terminate(self):
        logger.info("AA 记账插件已停用。")
