"""
Budget Allocator

Allocates budget to triggers based on performance scores and account balance.
"""

from typing import Dict


class BudgetAllocator:
    """
    Allocate budget based on account balance and performance scores.

    Formula:
    - total_budget = account_balance * risk_percentage
    - total_position_size = int(total_budget / contract_value)
    - Each trigger gets: (score / total_score) * total_position_size
    """

    def __init__(
        self,
        risk_percentage: float = 0.02,  # 2% of account
        contract_value: float = 15000.0,  # $15k per contract (e.g., NQ)
    ):
        """
        Initialize budget allocator.

        Args:
            risk_percentage: Percentage of account balance to risk
            contract_value: Value per contract (for position sizing)
        """
        self.risk_percentage = risk_percentage
        self.contract_value = contract_value

    def calculate_total_budget(self, account_balance: float) -> float:
        """
        Calculate total budget from account balance.

        Args:
            account_balance: Current account balance

        Returns:
            total_budget: Amount available for risk
        """
        return account_balance * self.risk_percentage

    def calculate_total_position_size(self, account_balance: float) -> int:
        """
        Calculate total position size (in contracts).

        Args:
            account_balance: Current account balance

        Returns:
            total_position_size: Maximum contracts to trade
        """
        total_budget = self.calculate_total_budget(account_balance)
        total_position_size = int(total_budget / self.contract_value)

        return max(1, total_position_size)  # At least 1 contract

    def allocate(
        self,
        trigger_scores: Dict[str, float],
        account_balance: float,
    ) -> Dict[str, float]:
        """
        Allocate position size to triggers based on scores.

        Args:
            trigger_scores: {trigger_name: score}
            account_balance: Current account balance

        Returns:
            {trigger_name: allocated_contracts}
        """
        # Calculate total position size
        total_position_size = self.calculate_total_position_size(account_balance)

        # Normalize scores (negative → 0)
        positive_scores = {
            name: max(0, score)
            for name, score in trigger_scores.items()
        }

        total_score = sum(positive_scores.values())

        # If all scores are 0 or negative
        if total_score <= 0:
            # Equal allocation
            equal_share = total_position_size / len(trigger_scores)
            return {
                name: equal_share
                for name in trigger_scores
            }

        # Allocate proportionally to scores
        allocation = {}
        for name, score in positive_scores.items():
            allocated = total_position_size * (score / total_score)
            allocation[name] = allocated

        return allocation

    def get_budget_info(self, account_balance: float) -> Dict:
        """
        Get budget information.

        Args:
            account_balance: Current account balance

        Returns:
            Budget info dictionary
        """
        total_budget = self.calculate_total_budget(account_balance)
        total_position_size = self.calculate_total_position_size(account_balance)

        return {
            'account_balance': account_balance,
            'risk_percentage': self.risk_percentage,
            'total_budget': total_budget,
            'contract_value': self.contract_value,
            'total_position_size': total_position_size,
        }
